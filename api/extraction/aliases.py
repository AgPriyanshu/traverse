"""Alias clustering cascade (S3.3) and its collision guard (S3.4).

Cheapest stage first; each stage only sees what the previous could not
resolve (``backend-1.md`` S3.3):

1. exact / normalised
2. honorific and name-order stripping
3. nickname / diminutive tables
4. contextual embedding similarity (be2's S3.8 service)
5. LLM adjudication on the residue only, batched

Every merge is guarded by ``collision.check`` — a string match a later stage
would happily merge is blocked outright when contextual evidence contradicts
it, and the cluster is flagged ``collision_suspected`` instead.
"""

import itertools
import logging
from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from ..contracts.enums import CandidateKind, LLMPurpose, ResolutionMethod
from ..db.models import BookCharacterCandidate
from ..llm import structured_call
from . import collision
from .normalization import (
    is_canonical_first_token,
    nickname_key,
    normalize,
    strip_honorifics,
    token_set_key,
)
from .prompts import ADJUDICATION_PROMPT
from .schemas import AdjudicationOutput

logger = logging.getLogger(__name__)

# Contexts sent per side of an adjudication prompt — enough for the model to
# judge co-presence/kinship/lifespan signals without paying for a candidate's
# entire (possibly hundred-mention) context list.
_MAX_CONTEXTS_PER_SIDE = 8


@dataclass
class Cluster:
    """A book-local group of surface forms believed to name one character."""

    canonical_name: str
    surface_forms: dict[str, ResolutionMethod]
    candidate_ids: set[UUID]
    contexts: list[dict]
    mention_counts: dict[str, int]
    collision_suspected: bool = False
    collision_reason: str | None = None
    collision_partner: str | None = None

    @property
    def cluster_key(self) -> str:
        return self.canonical_name

    @property
    def total_mentions(self) -> int:
        return sum(self.mention_counts.values())


def _choose_canonical(surface_forms: set[str], mention_counts: dict[str, int]) -> str:
    """Prefer the most complete, then the most frequent, surface form.

    "Elizabeth Bennet" over "Elizabeth" over "Lizzy" — a canonical name that
    disambiguates on its own is what S3.4 needs from every merge, not just
    the ones a collision was actually found in.
    """

    def sort_key(form: str) -> tuple[int, int, int]:
        token_count = len(form.split())

        return (
            token_count,
            int(is_canonical_first_token(form)),
            mention_counts.get(form, 0),
        )

    return max(surface_forms, key=sort_key)


def _seed_clusters(candidates: list[BookCharacterCandidate]) -> list[Cluster]:
    clusters = []
    for candidate in candidates:
        clusters.append(
            Cluster(
                canonical_name=candidate.surface_form,
                surface_forms={candidate.surface_form: ResolutionMethod.EXACT},
                candidate_ids={candidate.id},
                contexts=[
                    {**ctx, "surface_form": candidate.surface_form}
                    for ctx in candidate.contexts
                ],
                mention_counts={candidate.surface_form: candidate.mention_count},
            )
        )

    return clusters


def _combine(base: Cluster, other: Cluster, method: ResolutionMethod) -> Cluster:
    surface_forms = dict(base.surface_forms)
    for form, existing_method in other.surface_forms.items():
        surface_forms.setdefault(
            form,
            existing_method if existing_method != ResolutionMethod.EXACT else method,
        )

    all_forms = set(surface_forms) | {base.canonical_name, other.canonical_name}
    mention_counts = {**base.mention_counts, **other.mention_counts}

    return Cluster(
        canonical_name=_choose_canonical(all_forms, mention_counts),
        surface_forms=surface_forms,
        candidate_ids=base.candidate_ids | other.candidate_ids,
        contexts=base.contexts + other.contexts,
        mention_counts=mention_counts,
        collision_suspected=base.collision_suspected or other.collision_suspected,
    )


def _flag_collision(base: Cluster, other: Cluster, reason: str) -> None:
    base.collision_suspected = True
    other.collision_suspected = True
    base.collision_reason = other.collision_reason = reason
    base.collision_partner = other.canonical_name
    other.collision_partner = base.canonical_name


def _merge_by_key(
    clusters: list[Cluster], *, key_fn, method: ResolutionMethod
) -> list[Cluster]:
    groups: dict[str, list[Cluster]] = defaultdict(list)
    for cluster in clusters:
        key = key_fn(cluster.canonical_name)
        groups[key].append(cluster)

    merged: list[Cluster] = []
    for key, group in groups.items():
        if not key or len(group) == 1:
            merged.extend(group)
            continue

        base = group[0]
        for other in group[1:]:
            found = collision.check(
                base.canonical_name, other.canonical_name, base.contexts, other.contexts
            )
            if found is not None:
                _flag_collision(base, other, found.reason)
                merged.append(other)
                continue

            base = _combine(base, other, method)

        merged.append(base)

    return merged


def _blocking_pairs(clusters: list[Cluster]) -> list[tuple[Cluster, Cluster]]:
    """Candidate pairs worth an expensive comparison, via a cheap shared-token key.

    Without this, stage 4/5 would compare every cluster against every other
    one — the plan's own warning is that if the LLM stage sees thousands of
    pairs, stages 1-3 are underperforming, not that the LLM needs to see
    everything.
    """
    buckets: dict[tuple[str, str], list[Cluster]] = defaultdict(list)
    for cluster in clusters:
        tokens = strip_honorifics(cluster.canonical_name).split(" ")
        tokens = [t for t in tokens if t]
        if not tokens:
            continue
        buckets[("first", tokens[0])].append(cluster)
        buckets[("last", tokens[-1])].append(cluster)

    seen: set[frozenset[int]] = set()
    pairs: list[tuple[Cluster, Cluster]] = []
    for bucket in buckets.values():
        for a, b in itertools.combinations(bucket, 2):
            key = frozenset((id(a), id(b)))
            if key in seen:
                continue
            seen.add(key)
            pairs.append((a, b))

    return pairs


async def _merge_pairs_to_fixpoint(clusters: list[Cluster], decide) -> list[Cluster]:
    """Repeatedly merge blocked-together pairs until a full round finds none.

    A single pass over ``_blocking_pairs`` only ever merges disjoint pairs —
    once ``a`` merges into a combined cluster, any other pair naming the
    original ``a`` is skipped for that round. A residue group larger than
    two (six of Elizabeth's aliases, all sharing "Bennet") needs several
    rounds to fully consolidate, so this loops until one round makes no
    further progress rather than assuming one pass suffices.

    Args:
        clusters: Current clusters.
        decide: Async callable ``(a, b) -> ResolutionMethod | None`` —
            ``None`` means "do not merge this pair" (whether because it
            failed the stage's own test or because ``collision.check``
            blocked it; either way ``decide`` is responsible for flagging a
            collision itself before returning ``None``).

    Returns:
        Clusters after every reachable merge has been made.
    """
    result = list(clusters)

    while True:
        merged_out: set[int] = set()
        next_result: list[Cluster] = []

        for a, b in _blocking_pairs(result):
            if id(a) in merged_out or id(b) in merged_out:
                continue

            method = await decide(a, b)

            if method is None:
                continue

            combined = _combine(a, b, method)
            next_result.append(combined)
            merged_out.add(id(a))
            merged_out.add(id(b))

        if not merged_out:
            break

        next_result.extend(c for c in result if id(c) not in merged_out)
        result = next_result

    return result


async def _merge_by_embedding(clusters: list[Cluster]) -> list[Cluster]:
    from . import similarity  # noqa: PLC0415 — see similarity.py's own docstring.

    async def decide(a: Cluster, b: Cluster) -> ResolutionMethod | None:
        text_a = " ".join(c["context"] for c in a.contexts[:_MAX_CONTEXTS_PER_SIDE])
        text_b = " ".join(c["context"] for c in b.contexts[:_MAX_CONTEXTS_PER_SIDE])
        score = await similarity.context_similarity(text_a, text_b)

        if not similarity.is_similar(score):
            return None

        found = collision.check(
            a.canonical_name, b.canonical_name, a.contexts, b.contexts
        )
        if found is not None:
            _flag_collision(a, b, found.reason)

            return None

        return ResolutionMethod.EMBEDDING

    return await _merge_pairs_to_fixpoint(clusters, decide)


async def _merge_by_llm(clusters: list[Cluster], *, book_id: UUID) -> list[Cluster]:
    async def decide(a: Cluster, b: Cluster) -> ResolutionMethod | None:
        found = collision.check(
            a.canonical_name, b.canonical_name, a.contexts, b.contexts
        )
        if found is not None:
            _flag_collision(a, b, found.reason)

            return None

        decision = await _adjudicate(a, b, book_id=book_id)

        return ResolutionMethod.LLM if decision.same_person else None

    return await _merge_pairs_to_fixpoint(clusters, decide)


async def _adjudicate(a: Cluster, b: Cluster, *, book_id: UUID) -> AdjudicationOutput:
    contexts_a = "\n".join(
        f"(p{c['page']}) {c['context']}" for c in a.contexts[:_MAX_CONTEXTS_PER_SIDE]
    )
    contexts_b = "\n".join(
        f"(p{c['page']}) {c['context']}" for c in b.contexts[:_MAX_CONTEXTS_PER_SIDE]
    )
    prompt = ADJUDICATION_PROMPT.format(
        name_a=a.canonical_name,
        contexts_a=contexts_a,
        name_b=b.canonical_name,
        contexts_b=contexts_b,
    )

    decision = await structured_call(
        prompt,
        AdjudicationOutput,
        purpose=LLMPurpose.ADJUDICATE,
        book_id=str(book_id),
        stage="resolve_aliases",
    )

    return decision


async def cluster_candidates(
    candidates: list[BookCharacterCandidate], *, book_id: UUID
) -> list[Cluster]:
    """Run the full cascade over one book's surviving (person) candidates.

    Args:
        candidates: This book's ``BookCharacterCandidate`` rows, already
            past rejection (S3.2) — every one is assumed to be ``kind ==
            person``; callers that have not filtered will just see
            non-person candidates fail to cluster into anything meaningful.
        book_id: Tags the LLM adjudication stage's Langfuse trace.

    Returns:
        One ``Cluster`` per resolved character, book-local.
    """
    persons = [c for c in candidates if c.kind == CandidateKind.PERSON]

    clusters = _seed_clusters(persons)
    clusters = _merge_by_key(
        clusters, key_fn=normalize, method=ResolutionMethod.NORMALISED
    )
    clusters = _merge_by_key(
        clusters, key_fn=token_set_key, method=ResolutionMethod.HONORIFIC
    )
    clusters = _merge_by_key(
        clusters, key_fn=nickname_key, method=ResolutionMethod.NICKNAME
    )
    clusters = await _merge_by_embedding(clusters)
    clusters = await _merge_by_llm(clusters, book_id=book_id)

    return clusters

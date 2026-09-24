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

import asyncio
import itertools
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from ..contracts.enums import CandidateKind, LLMPurpose, ResolutionMethod
from ..db.models import BookCharacterCandidate
from ..llm import structured_call
from . import collision
from .filtering import plausible_character_name
from .generations import split_generations
from .normalization import (
    GENDERED_TITLES,
    content_tokens,
    gendered_title,
    honorific_of,
    is_canonical_first_token,
    normalize,
    strip_honorifics,
    titled_nickname_key,
    titled_token_set_key,
)
from .prompts import ADJUDICATION_PROMPT
from .schemas import AdjudicationOutput
from .sex import cluster_sexes, is_given_name, sex_conflict

logger = logging.getLogger(__name__)

# Contexts sent per side of an adjudication prompt — enough for the model to
# judge co-presence/kinship/lifespan signals without paying for a candidate's
# entire (possibly hundred-mention) context list.
_MAX_CONTEXTS_PER_SIDE = 8

# vLLM runs 16 sequences at once; adjudication shares it with nothing else in
# this stage, so half of that keeps the queue short without idling the GPU.
_ADJUDICATION_CONCURRENCY = 8

# A bare surname merges into the fuller cluster it names only when that
# cluster has this many times the mentions of any rival ("Darcy" is Mr. Darcy,
# not Miss Darcy). A given name never gets this: "Jane" stays unmerged if two
# clusters could claim it.
_SURNAME_DOMINANCE = 2.0


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
    """Prefer the most complete proper name, then the most frequent form.

    "Elizabeth Bennet" over "Elizabeth" over "Lizzy" — a canonical name that
    disambiguates on its own is what S3.4 needs from every merge. Completeness
    counts name tokens, not the honorific, so "Mr. Fitzwilliam Darcy" does not
    beat "Fitzwilliam Darcy" merely for its title, and an all-caps or
    punctuation-laden variant loses to a cleanly cased one.
    """

    def sort_key(form: str) -> tuple[int, int, int, int, int]:
        tokens = content_tokens(form)
        cleanly_cased = int(form == form.strip(" ._,") and not form.isupper())
        has_title = int(gendered_title(form) is not None)

        return (
            len(tokens),
            cleanly_cased,
            int(is_canonical_first_token(form)),
            mention_counts.get(form, 0),
            has_title,
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
        if not key.strip("|") or len(group) == 1:
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


def _honorifics_of(cluster: Cluster) -> set[str]:
    found = {honorific_of(form) for form in cluster.surface_forms}
    found.discard(None)

    return found  # type: ignore[return-value]


def _all_forms(cluster: Cluster) -> list[str]:
    forms = [cluster.canonical_name, *cluster.surface_forms]

    return forms


def _surname(cluster: Cluster) -> str | None:
    tokens = content_tokens(cluster.canonical_name)

    return tokens[-1] if tokens else None


def _is_bare_surname(cluster: Cluster) -> bool:
    tokens = content_tokens(cluster.canonical_name)
    bare = (
        len(tokens) == 1
        and honorific_of(cluster.canonical_name) is None
        and not is_given_name(tokens[0])
    )

    return bare


def _is_bare_titled_surname(cluster: Cluster, titles: frozenset[str]) -> bool:
    bare = (
        len(content_tokens(cluster.canonical_name)) == 1
        and honorific_of(cluster.canonical_name) in titles
    )

    return bare


def _has_given_name_form(cluster: Cluster, surname: str) -> bool:
    for form in _all_forms(cluster):
        tokens = content_tokens(form)
        if len(tokens) >= 2 and tokens[-1] == surname:
            return True

        if honorific_of(form) == "miss" and tokens == [surname]:
            return True

    return False


def _dominant(cluster: Cluster, siblings: list[Cluster]) -> bool:
    """Whether a cluster is the one a bare surname conventionally names.

    It must out-mention every rival by ``_SURNAME_DOMINANCE`` and must not be
    a woman: bare surnames name men, and women are "Miss Bennet" or "Elizabeth".
    """
    if cluster_sexes(_all_forms(cluster)) == {"f"}:
        return False

    rivals = [c.total_mentions for c in siblings if c is not cluster]
    dominant = not rivals or cluster.total_mentions >= _SURNAME_DOMINANCE * max(rivals)

    return dominant


def _surname_rule_vetoes(x: Cluster, y: Cluster, everyone: list[Cluster]) -> bool:
    """Rules about a form that names a family, not a person, and its rivals."""
    surname = _surname(x)
    siblings = [c for c in everyone if c is not x and _surname(c) == surname]

    if _is_bare_surname(x) and y in siblings:
        return not _dominant(y, siblings)

    if _is_bare_titled_surname(x, GENDERED_TITLES - {"mrs", "mistress"}):
        # "Miss Bennet" and "Mr. Earnshaw" name one of several same-sex family
        # members; picking one of them is a guess a model must not make.
        opposite = "m" if honorific_of(x.canonical_name) in {"miss", "ms"} else "f"
        candidates = [
            c
            for c in siblings
            if not _is_bare_surname(c)
            and len(content_tokens(c.canonical_name)) >= 2
            and cluster_sexes(_all_forms(c)) != {opposite}
        ]
        return y in candidates and len(candidates) >= 2

    if _is_bare_titled_surname(x, frozenset({"mrs", "lady", "mistress"})):
        # A married-woman title names a wife, distinct from any given-name
        # form of the family, but only when the family has a husband to be the
        # wife of. "Mrs. Dean" with no Mr. Dean is Ellen Dean.
        has_husband = any(
            c is not y and cluster_sexes(_all_forms(c)) == {"m"} for c in siblings
        )
        return has_husband and _has_given_name_form(y, surname or "")

    return False


def _may_be_same_person(a: Cluster, b: Cluster, everyone: list[Cluster]) -> bool:
    """Veto before a pair reaches the embedding or LLM stage, or a merge stands.

    A model can be talked into anything by two similar contexts, so the rules
    that must never be broken are checked here, in code: opposite sexes
    ("Mr. Bingley" is not "Caroline Bingley"), conflicting titles, different
    given names, a bare surname joining anything but its dominant cluster
    ("Darcy" is not "Miss Darcy"), "Miss Bennet" picking one of several
    sisters, and a bare "Lady Lucas" joining a "Charlotte Lucas".
    """
    if sex_conflict(_all_forms(a), _all_forms(b)):
        return False

    honorifics_a, honorifics_b = _honorifics_of(a), _honorifics_of(b)
    if honorifics_a and honorifics_b and honorifics_a.isdisjoint(honorifics_b):
        return False

    tokens_a, tokens_b = (
        content_tokens(a.canonical_name),
        content_tokens(b.canonical_name),
    )
    if len(tokens_a) >= 2 and len(tokens_b) >= 2 and tokens_a[0] != tokens_b[0]:
        return False

    vetoed = _surname_rule_vetoes(a, b, everyone) or _surname_rule_vetoes(
        b, a, everyone
    )

    return not vetoed


async def _merge_pairs_to_fixpoint(clusters: list[Cluster], decide) -> list[Cluster]:
    """Repeatedly merge blocked-together pairs until a full round finds none.

    Each round decides every candidate pair concurrently (bounded), then
    applies the merges in order, skipping a pair whose member was already
    merged this round. A residue group larger than two (six of Elizabeth's
    aliases, all sharing "Bennet") needs several rounds to consolidate, so
    this loops until a round makes no progress. Decisions are cached by the
    pair's member candidates: a pair judged "different" in round one is not
    paid for again in round two.

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
    gate = asyncio.Semaphore(_ADJUDICATION_CONCURRENCY)
    cache: dict[tuple[frozenset[UUID], frozenset[UUID]], ResolutionMethod | None] = {}

    async def cached(a: Cluster, b: Cluster) -> ResolutionMethod | None:
        key = (frozenset(a.candidate_ids), frozenset(b.candidate_ids))
        if key in cache:
            return cache[key]

        async with gate:
            cache[key] = await decide(a, b)

        return cache[key]

    while True:
        pairs = [
            (a, b)
            for a, b in _blocking_pairs(result)
            if _may_be_same_person(a, b, result)
        ]
        decisions = await asyncio.gather(*(cached(a, b) for a, b in pairs))

        merged_out: set[int] = set()
        next_result: list[Cluster] = []

        for (a, b), method in zip(pairs, decisions, strict=True):
            if method is None or id(a) in merged_out or id(b) in merged_out:
                continue

            next_result.append(_combine(a, b, method))
            merged_out.add(id(a))
            merged_out.add(id(b))

        if not merged_out:
            break

        next_result.extend(c for c in result if id(c) not in merged_out)
        result = next_result

    return result


def _subsumes(short: Cluster, long: Cluster) -> bool:
    """Whether ``long`` names the same person more completely than ``short``."""
    title_short = gendered_title(short.canonical_name)
    title_long = gendered_title(long.canonical_name)
    tokens_short = content_tokens(short.canonical_name)
    tokens_long = content_tokens(long.canonical_name)

    if title_short and title_long and title_short != title_long:
        return False

    if not tokens_short or short is long:
        return False

    if sex_conflict(_all_forms(short), _all_forms(long)):
        return False

    honorifics_short, honorifics_long = _honorifics_of(short), _honorifics_of(long)
    if (
        honorifics_short
        and honorifics_long
        and honorifics_short.isdisjoint(honorifics_long)
    ):
        return False

    # "Mr. Bennet" could be any male Bennet and "Colonel Fitzwilliam" is not
    # "Fitzwilliam Darcy", so a titled form only folds into a fuller form
    # carrying the same title; the model stage, which sees the contexts,
    # decides the rest.
    honorific_short = honorific_of(short.canonical_name)
    if (
        honorific_short
        and honorific_short != honorific_of(long.canonical_name)
        and not (honorific_short in GENDERED_TITLES and title_long is None)
    ):
        return False

    if len(tokens_long) > len(tokens_short):
        remaining = iter(tokens_long)

        return all(token in remaining for token in tokens_short)

    return (
        tokens_short == tokens_long and title_short is None and title_long is not None
    )


def _pick_subsuming_target(short: Cluster, targets: list[Cluster]) -> Cluster | None:
    if len(targets) == 1:
        return targets[0]

    tokens = content_tokens(short.canonical_name)
    bare_surname = (
        len(tokens) == 1
        and gendered_title(short.canonical_name) is None
        and all(content_tokens(t.canonical_name)[-1] == tokens[0] for t in targets)
    )
    if not bare_surname:
        return None

    ranked = sorted(targets, key=lambda t: t.total_mentions, reverse=True)
    if _dominant(ranked[0], targets):
        return ranked[0]

    return None


def _merge_subsumed(clusters: list[Cluster]) -> list[Cluster]:
    """Fold an incomplete form into the one fuller cluster it can only mean.

    "Elizabeth" into "Elizabeth Bennet", "Mr. Wickham" into "George Wickham",
    "Darcy" into "Mr. Darcy" (but not "Miss Darcy"). Ambiguous forms are left
    for the model stage rather than guessed, and every merge still passes the
    collision guard.
    """
    result = list(clusters)

    while True:
        changed = False

        for short in sorted(
            result, key=lambda c: len(content_tokens(c.canonical_name))
        ):
            targets = [other for other in result if _subsumes(short, other)]
            target = _pick_subsuming_target(short, targets) if targets else None

            if target is None or _surname_rule_vetoes(short, target, result):
                continue

            # Kinship phrases ("the younger son of his uncle") name relatives
            # near a surname; they cannot show that a shortened form of a name
            # is a different person from its own full form.
            found = collision.check(
                target.canonical_name,
                short.canonical_name,
                target.contexts,
                short.contexts,
                ignore_kinship=True,
            )
            if found is not None:
                _flag_collision(target, short, found.reason)
                continue

            combined = _combine(target, short, ResolutionMethod.HONORIFIC)
            result = [c for c in result if c is not short and c is not target]
            result.append(combined)
            changed = True

            break

        if not changed:
            break

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
    persons = [
        c
        for c in candidates
        if c.kind == CandidateKind.PERSON and plausible_character_name(c.surface_form)
    ]

    timings: list[str] = []

    def mark(stage: str, started: float, count: int) -> None:
        timings.append(f"{stage}={time.perf_counter() - started:.1f}s/{count}")

    started = time.perf_counter()
    clusters = _seed_clusters(persons)
    clusters = _merge_by_key(
        clusters, key_fn=normalize, method=ResolutionMethod.NORMALISED
    )
    clusters = _merge_by_key(
        clusters, key_fn=titled_token_set_key, method=ResolutionMethod.HONORIFIC
    )
    clusters = _merge_by_key(
        clusters, key_fn=titled_nickname_key, method=ResolutionMethod.NICKNAME
    )
    clusters = _merge_subsumed(clusters)
    mark("deterministic", started, len(clusters))

    started = time.perf_counter()
    clusters = await _merge_by_embedding(clusters)
    mark("embedding", started, len(clusters))

    started = time.perf_counter()
    clusters = await _merge_by_llm(clusters, book_id=book_id)
    mark("llm", started, len(clusters))

    clusters = split_generations(clusters)

    logger.info(
        "book %s alias cascade (stage/seconds/clusters left): %s",
        book_id,
        " ".join(timings),
    )

    return clusters

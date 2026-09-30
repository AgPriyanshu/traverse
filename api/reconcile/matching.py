import logging
from dataclasses import dataclass
from uuid import UUID

from ..contracts.enums import LLMPurpose, ResolutionMethod
from ..db.models import Character, CharacterDeath, Relation
from ..extraction import similarity
from ..extraction.normalization import (
    normalize,
    strip_honorifics,
    titled_nickname_key,
    titled_token_set_key,
)
from ..extraction.schemas import AdjudicationOutput
from ..llm import structured_call
from . import blocking
from .prompts import RECONCILE_ADJUDICATION_PROMPT
from .repository import BookCluster

logger = logging.getLogger(__name__)

_MAX_CONTEXTS_PER_SIDE = 8
_LLM_MERGE_THRESHOLD = 0.7

# Not a ``ResolutionMethod`` value: means "nothing was worth comparing", not
# "a stage ran and found no match" -- keeping it distinct from, say,
# ``ResolutionMethod.LLM`` at 0.0 confidence is what keeps the audit trail
# honest about which stages actually ran.
_METHOD_NONE = "none"


@dataclass
class MatchResult:
    """The outcome for one of this book's clusters against the project roster."""

    target: Character | None
    method: str
    confidence: float
    blocked_by: str | None = None
    # The candidate a block was raised against, kept separately from
    # ``target`` so a blocked match still carries enough to write a
    # ``merge_across_books`` review task -- ``target`` itself is ``None``
    # whenever ``blocked_by`` is set, precisely because it was never merged.
    blocked_target: Character | None = None


def _names(character: Character) -> set[str]:
    return {character.canonical_name, *character.aliases}


def _normalized_names(character: Character) -> set[str]:
    return {normalize(name) for name in _names(character)}


def _titled_keys(character: Character) -> set[str]:
    return {titled_token_set_key(name) for name in _names(character)}


def _nickname_keys(character: Character) -> set[str]:
    return {titled_nickname_key(name) for name in _names(character)}


def _blocking_tokens(character: Character) -> set[str]:
    """Every content token (honorifics stripped) across a character's known names.

    Every token, not just the first and last: cross-book rosters run to
    dozens of characters, not the hundreds a single book's within-book
    cascade has to bound with a first/last-token-only key, so scanning every
    token is cheap enough here and catches an epithet built around a middle
    name or surname ("the Barry girl" against "Diana Barry").
    """
    tokens: set[str] = set()
    for name in _names(character):
        parts = [t for t in strip_honorifics(name).split(" ") if t]
        tokens.update(parts)

    return tokens


def _prefiltered(book_char: Character, roster: list[Character]) -> list[Character]:
    """Roster characters worth an expensive comparison, via a shared name token.

    Same economy argument as the within-book cascade's ``_blocking_pairs``: if
    the LLM stage sees a candidate sharing no token with the book's cluster,
    stages 1-3 would already have caught anything real.
    """
    tokens = _blocking_tokens(book_char)
    if not tokens:
        return []

    return [target for target in roster if _blocking_tokens(target) & tokens]


def _deterministic_match(
    book_char: Character, roster: list[Character]
) -> tuple[Character, str, float] | None:
    book_normalized = _normalized_names(book_char)
    for target in roster:
        if book_normalized & _normalized_names(target):
            return target, ResolutionMethod.EXACT.value, 1.0

    book_titled = {k for k in _titled_keys(book_char) if k.strip("|")}
    for target in roster:
        if book_titled & _titled_keys(target):
            return target, ResolutionMethod.HONORIFIC.value, 0.9

    book_nick = {k for k in _nickname_keys(book_char) if k.strip("|")}
    for target in roster:
        if book_nick & _nickname_keys(target):
            return target, ResolutionMethod.NICKNAME.value, 0.85

    return None


async def _embedding_match(
    contexts: list[dict],
    pool: list[Character],
    context_map: dict[UUID, list[dict]],
) -> tuple[Character, float] | None:
    text_a = " ".join(c["context"] for c in contexts[:_MAX_CONTEXTS_PER_SIDE])

    for target in pool:
        target_contexts = context_map.get(target.id, [])
        if not target_contexts:
            continue

        text_b = " ".join(
            c["context"] for c in target_contexts[:_MAX_CONTEXTS_PER_SIDE]
        )
        score = await similarity.context_similarity(text_a, text_b)
        if similarity.is_similar(score):
            return target, 0.75

    return None


def _target_summary(target: Character) -> str:
    return (
        f"{target.importance_tier.value}, {target.mention_count} mentions "
        "project-wide so far"
    )


async def _adjudicate(
    book_char: Character,
    contexts: list[dict],
    target: Character,
    target_contexts: list[dict],
    *,
    book_id: UUID,
) -> AdjudicationOutput:
    candidate_text = "\n".join(
        f"(p{c['page']}) {c['context']}" for c in contexts[:_MAX_CONTEXTS_PER_SIDE]
    )
    target_text = (
        "\n".join(
            f"(p{c['page']}) {c['context']}"
            for c in target_contexts[:_MAX_CONTEXTS_PER_SIDE]
        )
        or "(no earlier context recorded)"
    )
    prompt = RECONCILE_ADJUDICATION_PROMPT.format(
        target_name=target.canonical_name,
        target_summary=_target_summary(target),
        target_contexts=target_text,
        candidate_name=book_char.canonical_name,
        candidate_contexts=candidate_text,
    )

    decision = await structured_call(
        prompt,
        AdjudicationOutput,
        purpose=LLMPurpose.ADJUDICATE,
        book_id=str(book_id),
        stage="reconcile_characters",
    )

    return decision


def _blocked(
    target: Character,
    cluster: BookCluster,
    *,
    book_order: int,
    deaths: dict[UUID, list[tuple[CharacterDeath, int]]],
    kinship: dict[UUID, list[Relation]],
    other_characters: dict[UUID, Character],
    context_map: dict[UUID, list[dict]],
    is_weak_signal: bool,
) -> str | None:
    reason = blocking.death_block(
        deaths.get(target.id, []), candidate_book_order=book_order
    )
    if reason:
        return reason

    reason = blocking.kinship_contradiction(
        kinship.get(target.id, []),
        target_id=target.id,
        other_characters=other_characters,
        candidate_contexts=cluster.contexts,
    )
    if reason:
        return reason

    reason = blocking.generational_namesake(
        target,
        cluster.character.canonical_name,
        context_map.get(target.id, []),
        cluster.contexts,
    )
    if reason:
        return reason

    reason = blocking.tier_implausible(
        target,
        candidate_tier=cluster.character.importance_tier,
        is_weak_signal=is_weak_signal,
    )
    if reason:
        return reason

    return None


async def match_cluster(
    cluster: BookCluster,
    *,
    roster: list[Character],
    context_map: dict[UUID, list[dict]],
    deaths: dict[UUID, list[tuple[CharacterDeath, int]]],
    kinship: dict[UUID, list[Relation]],
    other_characters: dict[UUID, Character],
    book_order: int,
    book_id: UUID,
) -> MatchResult:
    """Cascade one of this book's clusters against the project roster.

    Args:
        cluster: This book's resolved character, with its raw contexts.
        roster: Every other project character it could plausibly be.
        context_map: Raw contexts for roster characters, from other books.
        deaths: Roster character id -> its established deaths and their book order.
        kinship: Roster character id -> its established kinship relations.
        other_characters: Every character referenced by ``kinship``, by id.
        book_order: This book's series position.
        book_id: Tags the LLM adjudication stage's Langfuse trace.

    Returns:
        The match, a block, or neither (a genuinely new project character).
    """
    deterministic = _deterministic_match(cluster.character, roster)
    if deterministic is not None:
        target, method, confidence = deterministic
        reason = _blocked(
            target,
            cluster,
            book_order=book_order,
            deaths=deaths,
            kinship=kinship,
            other_characters=other_characters,
            context_map=context_map,
            is_weak_signal=False,
        )

        return MatchResult(
            target=None if reason else target,
            method=method,
            confidence=confidence,
            blocked_by=reason,
            blocked_target=target if reason else None,
        )

    pool = _prefiltered(cluster.character, roster)
    if not pool:
        return MatchResult(target=None, method=_METHOD_NONE, confidence=0.0)

    embedding = await _embedding_match(cluster.contexts, pool, context_map)
    if embedding is not None:
        target, confidence = embedding
        reason = _blocked(
            target,
            cluster,
            book_order=book_order,
            deaths=deaths,
            kinship=kinship,
            other_characters=other_characters,
            context_map=context_map,
            is_weak_signal=True,
        )

        return MatchResult(
            target=None if reason else target,
            method=ResolutionMethod.EMBEDDING.value,
            confidence=confidence,
            blocked_by=reason,
            blocked_target=target if reason else None,
        )

    for target in pool:
        decision = await _adjudicate(
            cluster.character,
            cluster.contexts,
            target,
            context_map.get(target.id, []),
            book_id=book_id,
        )
        if not decision.same_person:
            continue

        reason = _blocked(
            target,
            cluster,
            book_order=book_order,
            deaths=deaths,
            kinship=kinship,
            other_characters=other_characters,
            context_map=context_map,
            is_weak_signal=True,
        )
        if reason:
            return MatchResult(
                target=None,
                method=ResolutionMethod.LLM.value,
                confidence=decision.confidence,
                blocked_by=reason,
                blocked_target=target,
            )

        if decision.confidence >= _LLM_MERGE_THRESHOLD:
            return MatchResult(
                target=target,
                method=ResolutionMethod.LLM.value,
                confidence=decision.confidence,
            )

        # The middle band: the model leans "same person" but not strongly
        # enough to auto-merge. Bias tight -- route to review rather than
        # guess (backend-1.md S5.2's governing asymmetry).
        return MatchResult(
            target=None,
            method=ResolutionMethod.LLM.value,
            confidence=decision.confidence,
            blocked_by=(
                f"low-confidence LLM match ({decision.confidence:.2f}) against "
                f"{target.canonical_name!r}: {decision.reason}"
            ),
            blocked_target=target,
        )

    return MatchResult(target=None, method=ResolutionMethod.LLM.value, confidence=0.0)

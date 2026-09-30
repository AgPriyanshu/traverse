import difflib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.enums import ImportanceTier
from ..db.models import Character
from . import repository
from .normalization import (
    gendered_title,
    nickname_key,
    normalize,
    strip_honorifics,
    token_set_key,
)

# Below this, two unrelated short names (e.g. "Al" vs "Ann") drift into a
# false fuzzy match; above it a genuine one-character typo still clears.
_FUZZY_RATIO_THRESHOLD = 0.82

# Score bands, high to low, one per cascade stage. Two candidates tied within
# a band are a genuine ambiguity (see module docstring), not a ranking to
# break with a tiebreaker.
_SCORE_EXACT = 1.0
_SCORE_HONORIFIC = 0.9
_SCORE_NICKNAME = 0.85
_SCORE_PARTIAL = 0.6
_SCORE_RELATIVE = 0.95


class NameResolutionMethod(StrEnum):
    """How a phrase was matched to a character.

    Separate from ``api.contracts.enums.ResolutionMethod`` (frozen, and
    scoped to how a *mention cluster* was built during ingestion) — this is
    query-time-only and adds the two stages ingestion never needed: a bare
    partial/surname match, and a conversation-anchored relative term.
    """

    EXACT = "exact"
    HONORIFIC = "honorific"
    NICKNAME = "nickname"
    PARTIAL = "partial"
    FUZZY = "fuzzy"
    RELATIVE = "relative"


class CharacterRef(BaseModel):
    """One ranked candidate for a resolved name or reference."""

    character_id: UUID
    canonical_name: str
    score: float
    method: NameResolutionMethod
    importance_tier: ImportanceTier


# term -> predicate, read as "referent <predicate> candidate" — see
# ``repository.kinship_candidates``.
_RELATIVE_TERMS: dict[str, str] = {
    "sister": "sibling_of",
    "brother": "sibling_of",
    "sibling": "sibling_of",
    "siblings": "sibling_of",
    "wife": "married_to",
    "husband": "married_to",
    "spouse": "married_to",
    "mother": "child_of",
    "father": "child_of",
    "parent": "child_of",
    "mom": "child_of",
    "dad": "child_of",
    "daughter": "parent_of",
    "son": "parent_of",
    "child": "parent_of",
}

_PRONOUNS = frozenset({"her", "his", "their", "its"})


@dataclass(frozen=True)
class _RelativePhrase:
    predicate: str


def _parse_relative_phrase(text: str) -> _RelativePhrase | None:
    """Recognise a "her sister"-shaped phrase; ``None`` for anything else."""
    tokens = normalize(text).split(" ")

    if len(tokens) != 2 or tokens[0] not in _PRONOUNS:
        return None

    predicate = _RELATIVE_TERMS.get(tokens[1])
    if predicate is None:
        return None

    return _RelativePhrase(predicate=predicate)


async def _resolve_relative(
    session: SQLModelAsyncSession,
    *,
    project_id: UUID,
    phrase: _RelativePhrase,
    conversation_characters: Sequence[UUID],
    roster_by_id: dict[UUID, Character],
) -> list[CharacterRef]:
    if not conversation_characters:
        return []

    referent_id = conversation_characters[-1]
    candidate_ids = await repository.kinship_candidates(
        session,
        project_id=project_id,
        referent_id=referent_id,
        predicate=phrase.predicate,
    )

    refs = []
    for candidate_id in candidate_ids:
        character = roster_by_id.get(candidate_id)
        if character is None:
            continue

        refs.append(
            CharacterRef(
                character_id=character.id,
                canonical_name=character.canonical_name,
                score=_SCORE_RELATIVE,
                method=NameResolutionMethod.RELATIVE,
                importance_tier=character.importance_tier,
            )
        )

    return refs


def _forms(character: Character) -> list[str]:
    return [character.canonical_name, *character.aliases]


def _best_string_match(
    text: str, character: Character
) -> tuple[float, NameResolutionMethod] | None:
    """Return this character's best cascade match against ``text``, if any."""
    query_normalized = normalize(text)
    query_stripped = strip_honorifics(text)
    query_token_set = token_set_key(text)
    query_nickname = nickname_key(text)
    query_title = gendered_title(text)
    query_tokens = set(query_stripped.split(" ")) if query_stripped else set()

    best: tuple[float, NameResolutionMethod] | None = None

    for form in _forms(character):
        if not form:
            continue

        if query_normalized == normalize(form):
            return (_SCORE_EXACT, NameResolutionMethod.EXACT)

        form_title = gendered_title(form)
        form_stripped = strip_honorifics(form)
        form_tokens = set(form_stripped.split(" ")) if form_stripped else set()

        # "Mr. Darcy" and "Miss Darcy" are different characters (see
        # character-graph.md) — a title-stripped comparison must not confirm
        # a match at title-cascade confidence when both sides name a
        # different gendered title, however well the bare tokens line up.
        title_hard_conflict = (
            query_title is not None
            and form_title is not None
            and query_title != form_title
        )
        # A title known on only one side is a genuine signal, not noise, when
        # the surname alone is all either side has to go on ("Darcy" vs
        # "Miss Darcy") — dropping it there is exactly how a bare-surname
        # query would wrongly out-rank the very disambiguation the title
        # supplies. Downgrade rather than drop: it still surfaces, just not
        # at the same confidence as a name that matched with no title in play
        # anywhere, or one long enough (a given name present) to stand on
        # its own.
        title_one_sided = (query_title is None) != (form_title is None)
        title_one_sided_and_bare = title_one_sided and (
            len(query_tokens) <= 1 or len(form_tokens) <= 1
        )

        if (
            not title_hard_conflict
            and query_stripped
            and (
                query_stripped == form_stripped
                or query_token_set == token_set_key(form)
            )
        ):
            if title_one_sided_and_bare:
                best = _better(best, (_SCORE_PARTIAL, NameResolutionMethod.PARTIAL))
            else:
                best = _better(best, (_SCORE_HONORIFIC, NameResolutionMethod.HONORIFIC))
            continue

        if (
            not title_hard_conflict
            and not title_one_sided_and_bare
            and query_nickname
            and query_nickname == nickname_key(form)
        ):
            best = _better(best, (_SCORE_NICKNAME, NameResolutionMethod.NICKNAME))
            continue

        if query_tokens and query_tokens.issubset(form_tokens):
            best = _better(best, (_SCORE_PARTIAL, NameResolutionMethod.PARTIAL))
            continue

        if query_stripped and form_stripped:
            ratio = difflib.SequenceMatcher(None, query_stripped, form_stripped).ratio()
            if ratio >= _FUZZY_RATIO_THRESHOLD:
                best = _better(
                    best, (ratio * _SCORE_PARTIAL, NameResolutionMethod.FUZZY)
                )

    return best


def _better(
    current: tuple[float, NameResolutionMethod] | None,
    candidate: tuple[float, NameResolutionMethod],
) -> tuple[float, NameResolutionMethod]:
    if current is None or candidate[0] > current[0]:
        return candidate

    return current


async def resolve_names(
    session: SQLModelAsyncSession,
    project_id: UUID,
    text: str,
    *,
    conversation_characters: Sequence[UUID] | None = None,
) -> list[CharacterRef]:
    """Resolve one phrase from a question to ranked candidate characters.

    Project-scoped, not book-scoped: a series project's roster spans every
    book in it, so "Anne" resolves the same way whichever volume the
    question is about.

    The cascade, cheapest and most specific first: exact/normalised ->
    honorific/name-order -> nickname -> partial (bare surname or given name)
    -> fuzzy (typo tolerance) -> conversation-anchored relative term ("her
    sister"). Reuses the Sprint 3 alias primitives
    (:mod:`api.extraction.normalization`) rather than a second implementation
    of the same string folding.

    Args:
        session: An open database session.
        project_id: The project whose roster to resolve against.
        text: The phrase to resolve, e.g. ``"Lizzy"``, ``"Darcy"``, or
            ``"her sister"``.
        conversation_characters: Characters already resolved earlier in the
            current conversation, oldest first. Required to resolve a
            pronoun-plus-relative phrase — without it, such a phrase resolves
            to nothing rather than guessing. Wiring this to a live
            conversation is be2's S6.6; this parameter exists so that wiring
            is a call-site change, not a signature change.

    Returns:
        Ranked candidates, highest score first. Empty when nothing matches.
        More than one entry at the same top score is a genuine ambiguity —
        callers must not silently pick the first one.
    """
    roster = await repository.list_project_roster(session, project_id)
    if not roster:
        return []

    roster_by_id = {character.id: character for character in roster}

    relative_phrase = _parse_relative_phrase(text)
    if relative_phrase is not None:
        return await _resolve_relative(
            session,
            project_id=project_id,
            phrase=relative_phrase,
            conversation_characters=conversation_characters or (),
            roster_by_id=roster_by_id,
        )

    scored: list[CharacterRef] = []
    for character in roster:
        match = _best_string_match(text, character)
        if match is None:
            continue

        score, method = match
        scored.append(
            CharacterRef(
                character_id=character.id,
                canonical_name=character.canonical_name,
                score=score,
                method=method,
                importance_tier=character.importance_tier,
            )
        )

    scored.sort(key=lambda ref: (-ref.score, ref.canonical_name))

    return scored

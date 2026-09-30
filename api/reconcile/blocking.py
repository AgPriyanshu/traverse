import re
from uuid import UUID

from ..contracts.enums import ImportanceTier
from ..db.models import Character, CharacterDeath, Relation
from ..extraction import collision
from ..extraction.normalization import strip_honorifics

_PARENT_WORDS = ("mother", "father", "parent")
_CHILD_WORDS = ("son", "daughter", "child")
_KINSHIP_DIRECTION_RE = re.compile(
    r"\b(mother|father|parent|son|daughter|child)\s+of\b", re.IGNORECASE
)

_TIER_RANK = {
    ImportanceTier.MENTIONED: 0,
    ImportanceTier.MINOR: 1,
    ImportanceTier.MAJOR: 2,
    ImportanceTier.PROTAGONIST: 3,
}
# A weak-signal (embedding/LLM) match promoting a candidate this far past its
# own book's tier is suspicious, not confirmatory (backend-1.md S5.2).
_TIER_JUMP_SUSPICIOUS = 2


def death_block(
    deaths: list[tuple[CharacterDeath, int]], *, candidate_book_order: int
) -> str | None:
    """Block a match if the target's death was established in an earlier book.

    A later book naming the same surface form is a namesake, a flashback, or
    a resurrection -- never an automatic link. An appearance in a book at or
    before the death's own book is a normal, living appearance (a flashback
    scene or the death's own book), not a contradiction.
    """
    for death, death_book_order in deaths:
        if candidate_book_order > death_book_order:
            chapter = f", ch. {death.chapter}" if death.chapter is not None else ""

            return (
                f"death established in book {death_book_order}{chapter}; this "
                f"appearance is in a later book"
            )

    return None


def _kinship_word(text: str) -> str | None:
    match = _KINSHIP_DIRECTION_RE.search(text)

    return match.group(1).lower() if match else None


def _kinship_word_in_predicate(predicate: str) -> str | None:
    lowered = predicate.lower()
    for word in (*_PARENT_WORDS, *_CHILD_WORDS):
        if word in lowered:
            return word

    return None


def _mentions(text: str, name: str) -> bool:
    given = (strip_honorifics(name).split(" ") or [""])[0]

    return bool(given) and given.lower() in text.lower()


def kinship_contradiction(
    target_relations: list[Relation],
    *,
    target_id: UUID,
    other_characters: dict[UUID, Character],
    candidate_contexts: list[dict],
) -> str | None:
    """Block if this book's text contradicts an already-established kinship edge.

    "The project says X is Y's mother; this book says X is Y's daughter" --
    Sprint 5's cross-book version of the two-Catherines problem. Flags a
    contradiction when a candidate's own context names the other party to an
    established kinship edge alongside the OPPOSITE direction word.
    """
    for relation in target_relations:
        other_id = (
            relation.object_character_id
            if relation.subject_character_id == target_id
            else relation.subject_character_id
        )
        other = other_characters.get(other_id)
        if other is None:
            continue

        established = _kinship_word_in_predicate(relation.predicate)
        if established is None:
            continue

        opposite = _CHILD_WORDS if established in _PARENT_WORDS else _PARENT_WORDS

        for context in candidate_contexts:
            text = context.get("context", "")
            if not _mentions(text, other.canonical_name):
                continue

            found = _kinship_word(text)
            if found in opposite:
                return (
                    f"established {relation.predicate} relation to "
                    f"{other.canonical_name!r} contradicted by this book's text: "
                    f"{text!r}"
                )

    return None


def generational_namesake(
    target: Character,
    candidate_name: str,
    target_contexts: list[dict],
    candidate_contexts: list[dict],
) -> str | None:
    """Block on a generational marker or a disjoint lifespan at series distance.

    Reuses the within-book collision guard's generational and lifespan checks
    (``api/extraction/collision.py``) -- the phrase and page-order reasoning is
    identical, only the distance between the two mentions is greater. Kinship
    phrasing is ignored here; :func:`kinship_contradiction` is the dedicated,
    relation-aware check for that signal.
    """
    found = collision.check(
        target.canonical_name,
        candidate_name,
        target_contexts,
        candidate_contexts,
        ignore_kinship=True,
    )

    return found.reason if found is not None else None


def tier_implausible(
    target: Character, *, candidate_tier: ImportanceTier, is_weak_signal: bool
) -> str | None:
    """Block a weak-signal match that jumps too far up the tier ladder.

    A protagonist-tier match against a mentioned-once candidate is suspicious,
    not confirmatory -- it is exactly the shape of a coincidental-embedding or
    an over-eager LLM call, so it is only checked for the stages that produce
    exactly that kind of weak, non-deterministic evidence.
    """
    if not is_weak_signal:
        return None

    jump = _TIER_RANK[target.importance_tier] - _TIER_RANK[candidate_tier]
    if jump >= _TIER_JUMP_SUSPICIOUS:
        return (
            f"tier jump implausible: candidate is {candidate_tier.value}, "
            f"target is {target.importance_tier.value}"
        )

    return None

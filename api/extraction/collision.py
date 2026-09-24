"""Name-collision guard (S3.4) — the two-Catherines case.

Two characters can share a name. String evidence says "merge"; contextual
evidence can say "split". This module is consulted by every stage of the
alias cascade (``aliases.py``) immediately before it commits a merge — a
false merge here is silent and effectively unrecoverable (PRD's own words),
so the guard runs even at the cheap deterministic stages where a collision is
unlikely, not only at the LLM stage where it is expected.
"""

import re
from dataclasses import dataclass

from .normalization import strip_honorifics

_GENERATIONAL_MARKERS = r"young|younger|elder|eldest|senior|junior|old|older"
_DEATH_RE = re.compile(
    r"\b(died|death of|dead|buried|her grave|his grave|passed away)\b",
    re.IGNORECASE,
)
_KINSHIP_RE = re.compile(
    r"\b(mother|father|daughter|son|parent|child)\s+of\b"
    r"|\bher mother'?s name\b|\bhis father'?s name\b|\bnamed after\b",
    re.IGNORECASE,
)


@dataclass
class Collision:
    reason: str


def _shares_first_token_distinct_qualifier(name_a: str, name_b: str) -> bool:
    """Same given name, different (non-nickname) surname or qualifier.

    This alone resolves the headline case: "Catherine Earnshaw" and
    "Catherine Linton" share a first token but nothing else, which is already
    strong evidence of two people — no generational language or contextual
    inference required.
    """
    tokens_a = strip_honorifics(name_a).split(" ")
    tokens_b = strip_honorifics(name_b).split(" ")

    if len(tokens_a) < 2 or len(tokens_b) < 2:
        return False

    if tokens_a[0] != tokens_b[0]:
        return False

    return tokens_a[1:] != tokens_b[1:]


def _context_texts(contexts: list[dict]) -> list[tuple[int, str]]:
    return [(c["page"], c["context"]) for c in contexts]


def _generational_conflict(
    name_a: str,
    name_b: str,
    contexts_a: list[dict],
    contexts_b: list[dict],
) -> str | None:
    """A marker counts only when it qualifies one of the names being compared.

    "the old lady" or "the eldest Miss Bennet" says nothing about whether
    "Elizabeth" and "Elizabeth Bennet" are two people; "young Catherine" does.
    """
    tokens = {
        token
        for name in (name_a, name_b)
        for token in strip_honorifics(name).split(" ")
        if len(token) >= 3
    }
    if not tokens:
        return None

    pattern = re.compile(
        rf"\b(?:{_GENERATIONAL_MARKERS})\s+"
        rf"(?:(?:miss|mrs?|lady|sir)\.?\s+)?(?:{'|'.join(map(re.escape, tokens))})\b",
        re.IGNORECASE,
    )
    for contexts in (contexts_a, contexts_b):
        for _, text in _context_texts(contexts):
            match = pattern.search(text)
            if match:
                return f"generational marker in context: {match.group(0)!r}"

    return None


def _kinship_conflict(
    name_a: str,
    name_b: str,
    contexts_a: list[dict],
    contexts_b: list[dict],
) -> str | None:
    for name, contexts in ((name_b, contexts_a), (name_a, contexts_b)):
        for _, text in _context_texts(contexts):
            given = (strip_honorifics(name).split(" ") or [""])[0]
            if _KINSHIP_RE.search(text) and given and given in text.lower():
                return f"kinship phrase links {name_a!r} and {name_b!r}: {text!r}"

    return None


def _lifespan_conflict(contexts_a: list[dict], contexts_b: list[dict]) -> str | None:
    def death_page(contexts: list[dict]) -> int | None:
        pages = [
            page for page, text in _context_texts(contexts) if _DEATH_RE.search(text)
        ]

        return min(pages) if pages else None

    def first_page(contexts: list[dict]) -> int | None:
        pages = [page for page, _ in _context_texts(contexts)]

        return min(pages) if pages else None

    death_a, death_b = death_page(contexts_a), death_page(contexts_b)
    first_a, first_b = first_page(contexts_a), first_page(contexts_b)

    if (
        death_a is not None
        and first_b is not None
        and first_b > death_a
        and all(page > death_a for page, _ in _context_texts(contexts_b))
    ):
        return f"first mention (p{first_b}) is after an earlier death (p{death_a})"

    if (
        death_b is not None
        and first_a is not None
        and first_a > death_b
        and all(page > death_b for page, _ in _context_texts(contexts_a))
    ):
        return f"first mention (p{first_a}) is after an earlier death (p{death_b})"

    return None


def check(
    name_a: str,
    name_b: str,
    contexts_a: list[dict],
    contexts_b: list[dict],
) -> Collision | None:
    """Decide whether contextual evidence blocks merging ``name_a`` and ``name_b``.

    Checked cheapest and most reliable first. Any single hit blocks the
    merge — this is deliberately not a confidence tiebreak (``api/AGENTS.md``
    domain invariants apply one level up to relations, but the same
    reasoning holds here: over-merging is silent and destructive, so one
    piece of contradicting evidence outweighs any amount of string
    similarity).

    Args:
        name_a: Cluster A's current canonical name.
        name_b: Cluster B's current canonical name.
        contexts_a: Cluster A's merged context entries (``page``, ``context``).
        contexts_b: Cluster B's merged context entries.

    Returns:
        A ``Collision`` with the human-readable reason, or ``None`` if
        nothing blocks the merge.
    """
    if _shares_first_token_distinct_qualifier(name_a, name_b):
        return Collision(
            f"{name_a!r} and {name_b!r} share a given name but differ in "
            "surname or qualifier"
        )

    reason = _generational_conflict(name_a, name_b, contexts_a, contexts_b)
    if reason:
        return Collision(reason)

    reason = _kinship_conflict(name_a, name_b, contexts_a, contexts_b)
    if reason:
        return Collision(reason)

    reason = _lifespan_conflict(contexts_a, contexts_b)
    if reason:
        return Collision(reason)

    return None

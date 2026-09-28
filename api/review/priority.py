"""Review task priority: blast radius, not arrival order (S7.3, F5.3).

A ``merge_characters`` decision on a protagonist repoints every mention and
relation that character carries; a ``confirm_relation`` on a minor pair
repoints at most one edge. Priority is a function of the importance tier of
the characters a decision touches and how many mentions/edges it can move —
never insertion order, and never ``task_type`` alone (a `merge_across_books`
on a protagonist must still outrank a `resolve_conflict` between two minors).
"""

from collections.abc import Iterable

from ..contracts.enums import ImportanceTier, ReviewTaskType

_TIER_WEIGHT: dict[ImportanceTier, int] = {
    ImportanceTier.PROTAGONIST: 1000,
    ImportanceTier.MAJOR: 300,
    ImportanceTier.MINOR: 50,
    ImportanceTier.MENTIONED: 10,
}

# How much of a decision's own blast radius actually lands, once tier is
# already weighted in: a merge repoints every mention and edge the character
# owns, a conflict resolves a couple of edges, a confirm resolves one, and
# classify/chapter decisions are informational rather than structural.
_TASK_MULTIPLIER: dict[ReviewTaskType, float] = {
    ReviewTaskType.MERGE_CHARACTERS: 1.0,
    ReviewTaskType.MERGE_ACROSS_BOOKS: 1.0,
    ReviewTaskType.RESOLVE_CONFLICT: 0.5,
    ReviewTaskType.CONFIRM_RELATION: 0.25,
    ReviewTaskType.CLASSIFY_CANDIDATE: 0.05,
    ReviewTaskType.CONFIRM_CHAPTER_SPLIT: 0.05,
}


def tier_weight(tier: ImportanceTier | None) -> int:
    if tier is None:
        return 0

    return _TIER_WEIGHT.get(tier, 0)


def highest_tier(tiers: Iterable[ImportanceTier]) -> ImportanceTier | None:
    """Return the most prominent tier among ``tiers``, or ``None`` if empty."""
    ranked = sorted(tiers, key=tier_weight, reverse=True)

    return ranked[0] if ranked else None


def blast_radius(
    *,
    task_type: ReviewTaskType,
    max_tier: ImportanceTier | None,
    cascade: int = 0,
) -> int:
    """Score one review task by how much of the graph its decision can move.

    Args:
        task_type: What kind of decision this is.
        max_tier: The highest importance tier among the characters involved.
        cascade: A rough count of mentions/edges the decision would repoint
            or recompute — the tie-break within one tier, not the primary
            signal (a protagonist decision always outranks a mentioned-tier
            one, whatever the cascade count says).

    Returns:
        A priority score, higher sorts first. Comparable within one project's
        queue only — it is not calibrated across projects.
    """
    tier_score = tier_weight(max_tier)
    base = tier_score * 10 + max(cascade, 0)
    multiplier = _TASK_MULTIPLIER.get(task_type, 0.25)

    return round(base * multiplier)

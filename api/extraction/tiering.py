"""Importance tiering (S3.5, PRD §12.5) — two methods behind a flag, measured.

``TIERING_METHOD`` is read straight from the environment rather than
``api.config.settings`` because that file is orchestrator-owned as of the
Sprint 2 freeze (``BRANCH.md``) and this flag did not exist at the Sprint 3
freeze — SCR filed in ``plans/sprint-3/SCR.md`` to promote it to a real
settings key; non-blocking here since a plain env read behaves identically.
"""

import os

from ..contracts.enums import ImportanceTier

# Relative-to-the-busiest-character thresholds, not rank percentiles. A
# percentile band (e.g. "top 5%") collapses to a single character on a small
# cast and would only ever tier one protagonist even when the book clearly
# has two (Elizabeth *and* Darcy) — comparing to the maximum observed score
# instead lets every character close to the busiest one tier as protagonist,
# however many that turns out to be.
_PROTAGONIST_RATIO = 0.5
_MAJOR_RATIO = 0.15
_MINOR_RATIO = 0.03


def _tier_from_relative_score(score: float, max_score: float) -> ImportanceTier:
    if max_score <= 0:
        return ImportanceTier.MENTIONED

    ratio = score / max_score

    if ratio >= _PROTAGONIST_RATIO:
        return ImportanceTier.PROTAGONIST
    if ratio >= _MAJOR_RATIO:
        return ImportanceTier.MAJOR
    if ratio >= _MINOR_RATIO:
        return ImportanceTier.MINOR

    return ImportanceTier.MENTIONED


def tier_by_mention_count(mention_counts: dict[str, int]) -> dict[str, ImportanceTier]:
    """Tier by raw mention volume alone."""
    if not mention_counts:
        return {}

    max_count = max(mention_counts.values())

    return {
        name: _tier_from_relative_score(count, max_count)
        for name, count in mention_counts.items()
    }


def tier_by_participation(
    chapter_counts: dict[str, int], chunk_counts: dict[str, int]
) -> dict[str, ImportanceTier]:
    """Tier by breadth of appearance rather than raw volume.

    Scored as ``3 * distinct chapters + distinct chunks``. The plan's own
    definition is scene count + dialogue-line count + distinct chapters;
    ``scene``/``dialogue_line`` are S4 tables with no data yet this sprint,
    so distinct chunks stands in for scene breadth until that lands — a
    documented approximation, not a silent one, and the reason this method
    needs remeasuring once S4's real signal exists.
    """
    names = set(chapter_counts) | set(chunk_counts)
    scores = {
        name: 3 * chapter_counts.get(name, 0) + chunk_counts.get(name, 0)
        for name in names
    }

    if not scores:
        return {}

    max_score = max(scores.values())

    return {
        name: _tier_from_relative_score(score, max_score)
        for name, score in scores.items()
    }


def active_method() -> str:
    """Return the configured tiering method, defaulting to ``mention_count``."""
    method = os.getenv("TIERING_METHOD", "mention_count")

    return method if method in ("mention_count", "participation") else "mention_count"

"""Adapter to be2's mention-context similarity service (S3.8).

``api/graph/**`` is be2-owned (``BRANCH.md``) and is built in the same sprint
this module is, in a parallel worktree — the function this calls may not
exist yet when this code runs. The import is deferred to call time and
degrades to "no additional merges" rather than failing the whole cascade, so
be1's stage 4 comes online automatically the moment be2's branch merges,
with nothing to change on this side.
"""

import logging

logger = logging.getLogger(__name__)

_SIMILARITY_THRESHOLD = 0.82


async def context_similarity(text_a: str, text_b: str) -> float | None:
    """Return be2's contextual similarity score for two mention contexts.

    Returns:
        A score in ``[0, 1]``, or ``None`` if be2's service is not available
        in this checkout — the caller treats ``None`` as "cannot compare",
        not as "definitely different".
    """
    try:
        from api.graph.similarity import cluster_contexts  # noqa: PLC0415
    except ImportError:
        logger.debug(
            "api.graph.similarity not available yet; skipping embedding-similarity "
            "alias stage (S3.8 not merged into this checkout)"
        )

        return None

    return await cluster_contexts(text_a, text_b)


def is_similar(score: float | None) -> bool:
    """Whether a similarity score clears the merge threshold."""
    return score is not None and score >= _SIMILARITY_THRESHOLD

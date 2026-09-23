"""Adapter to be2's mention-context similarity service (S3.8).

``api/graph/**`` is be2-owned (``BRANCH.md``) and is built in the same sprint
this module is, in a parallel worktree — the function this calls may not
exist yet when this code runs. The import is deferred to call time and
degrades to "no additional merges" rather than failing the whole cascade, so
be1's stage 4 comes online automatically the moment be2's branch merges,
with nothing to change on this side.

``api.graph.similarity.cluster_contexts`` is a **batch** clustering function
over ``MentionContext(mention_id, context)`` objects
(``plans/sprint-3/backend-2.md`` S3.8), not a pairwise similarity score —
this adapter's job is entirely to bridge that batch API to the pairwise
``decide(a, b)`` shape ``aliases.py``'s cascade wants, by asking it to
cluster exactly two contexts and checking whether they landed in one cluster
or two.
"""

import logging
from uuid import uuid4

logger = logging.getLogger(__name__)


async def context_similarity(text_a: str, text_b: str) -> bool | None:
    """Ask be2's clustering service whether two mention contexts read as one person.

    Returns:
        ``True`` if clustering the pair together produces one cluster,
        ``False`` if it produces two, or ``None`` if be2's service is not
        available in this checkout — the caller treats ``None`` as "cannot
        compare", not as "definitely different".
    """
    try:
        from api.graph.similarity import (  # noqa: PLC0415
            MentionContext,
            cluster_contexts,
            similarity_threshold,
        )
    except ImportError:
        logger.debug(
            "api.graph.similarity not available yet; skipping embedding-similarity "
            "alias stage (S3.8 not merged into this checkout)"
        )

        return None

    # Arbitrary ids: this stage compares aggregated cluster-level context
    # text, not real individual mentions, so there is no mention_id to reuse.
    mentions = [
        MentionContext(mention_id=uuid4(), context=text_a),
        MentionContext(mention_id=uuid4(), context=text_b),
    ]
    clusters = await cluster_contexts(mentions, threshold=similarity_threshold())

    return len(clusters) == 1


def is_similar(result: bool | None) -> bool:
    """Whether the pair clustered together."""
    return result is True

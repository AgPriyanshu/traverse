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

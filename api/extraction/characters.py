"""Character record assembly (S3.5) — tiering and attributes over resolved clusters.

Turns the alias cascade's ``Cluster`` objects into the plain dicts
``api.extraction.repository.persist_characters`` writes. Kept separate from
the cascade itself so tiering can be re-measured (``backend-1.md``'s
mention-count vs. participation comparison) without touching clustering.
"""

from uuid import UUID

from ..contracts.enums import ResolutionMethod
from . import attributes as attribute_extraction
from . import tiering
from .aliases import Cluster


def _distinct_chapters(cluster: Cluster) -> int:
    chapters = {
        c["chapter_number"] for c in cluster.contexts if c["chapter_number"] is not None
    }

    return len(chapters)


def _distinct_chunks(cluster: Cluster) -> int:
    chunks = {c["chunk_id"] for c in cluster.contexts}

    return len(chunks)


def _first_and_last(cluster: Cluster) -> tuple[int, int | None, int, int | None]:
    by_page = sorted(cluster.contexts, key=lambda c: c["page"])
    first, last = by_page[0], by_page[-1]

    return first["page"], first["chapter_number"], last["page"], last["chapter_number"]


def _assign_tiers(clusters: list[Cluster]) -> dict[str, str]:
    method = tiering.active_method()

    if method == "participation":
        chapter_counts = {c.canonical_name: _distinct_chapters(c) for c in clusters}
        chunk_counts = {c.canonical_name: _distinct_chunks(c) for c in clusters}
        tiers = tiering.tier_by_participation(chapter_counts, chunk_counts)
    else:
        mention_counts = {c.canonical_name: c.total_mentions for c in clusters}
        tiers = tiering.tier_by_mention_count(mention_counts)

    return tiers


async def build_character_rows(clusters: list[Cluster], *, book_id: UUID) -> list[dict]:
    """Build persistable rows for every resolved cluster of one book.

    Args:
        clusters: Output of ``api.extraction.aliases.cluster_candidates``.
        book_id: Tags every attribute-extraction call's Langfuse trace.

    Returns:
        One dict per cluster, shaped for
        ``api.extraction.repository.persist_characters``.
    """
    tiers = _assign_tiers(clusters)
    rows: list[dict] = []

    for cluster in clusters:
        first_page, first_chapter, last_page, last_chapter = _first_and_last(cluster)
        character_attributes = await attribute_extraction.extract_attributes(
            cluster.canonical_name, cluster.contexts, book_id=book_id
        )

        mentions = [
            {
                "chunk_id": context["chunk_id"],
                "surface_form": context["surface_form"],
                "page": context["page"],
                "resolution_method": cluster.surface_forms.get(
                    context["surface_form"], ResolutionMethod.EXACT
                ),
            }
            for context in cluster.contexts
        ]

        rows.append(
            {
                "canonical_name": cluster.canonical_name,
                "aliases": sorted(cluster.surface_forms),
                "importance_tier": tiers.get(cluster.canonical_name),
                "first_page": first_page,
                "first_chapter": first_chapter,
                "last_page": last_page,
                "last_chapter": last_chapter,
                "mention_count": cluster.total_mentions,
                "attributes": character_attributes,
                "collision_suspected": cluster.collision_suspected,
                "mentions": mentions,
            }
        )

    return rows

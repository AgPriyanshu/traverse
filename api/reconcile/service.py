"""Top-level orchestration for ``pipeline.reconcile_characters`` (S5.1-S5.3).

Cascades one book's already-persisted clusters against the rest of the
project's roster, merges what the cascade and the blocking gate agree is the
same person, queues review for anything blocked, and recomputes every touched
character's derived fields from its full appearance set -- never accumulated,
which is what makes S5.4's order-independence guarantee hold.
"""

import logging
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from . import matching, repository

logger = logging.getLogger(__name__)


async def reconcile_book(
    session: SQLModelAsyncSession, *, book_id: UUID, project_id: UUID
) -> int:
    """Reconcile one book's roster against the project's roster.

    Args:
        session: Open session; the repository calls this makes each commit.
        book_id: The book whose ``resolve_aliases`` output is being reconciled.
        project_id: The book's project -- the scope of the roster it joins.

    Returns:
        The number of this book's clusters considered, for
        ``StageRecord.rows_written``.
    """
    clusters = await repository.list_book_clusters(session, book_id)
    if not clusters:
        return 0

    book_order = await repository.get_book_order(session, book_id)
    exclude_ids = {cluster.character.id for cluster in clusters}
    roster = await repository.list_roster_characters(session, project_id, exclude_ids)
    context_map = await repository.context_map_for(
        session, project_id, exclude_book_id=book_id
    )

    roster_ids = {character.id for character in roster}
    deaths = await repository.list_deaths(session, roster_ids)
    kinship = await repository.list_kinship_relations(session, roster_ids)

    other_ids = {
        relation.subject_character_id
        for relations in kinship.values()
        for relation in relations
    } | {
        relation.object_character_id
        for relations in kinship.values()
        for relation in relations
    }
    other_characters = {c.id: c for c in roster if c.id in other_ids}
    # A kinship partner not itself in the roster pool (already merged
    # elsewhere, or with no appearance in another book) is fetched
    # individually -- the kinship check needs its name regardless.
    for character_id in other_ids - set(other_characters):
        character = await repository.get_character(session, character_id)
        if character is not None:
            other_characters[character_id] = character

    touched_character_ids: set[UUID] = set()

    for cluster in clusters:
        result = await matching.match_cluster(
            cluster,
            roster=roster,
            context_map=context_map,
            deaths=deaths,
            kinship=kinship,
            other_characters=other_characters,
            book_order=book_order,
            book_id=book_id,
        )

        if result.target is not None:
            await repository.merge_character(
                session, source_id=cluster.character.id, target_id=result.target.id
            )
            final_character_id = result.target.id
        else:
            final_character_id = cluster.character.id

        touched_character_ids.add(final_character_id)

        if result.blocked_by and result.blocked_target is not None:
            await repository.queue_cross_book_review(
                session,
                project_id=project_id,
                book_id=book_id,
                candidate=cluster.character,
                target=result.blocked_target,
                reason=result.blocked_by,
                confidence=result.confidence,
            )

        await repository.record_decision(
            session,
            book_id=book_id,
            cluster_key=cluster.character.canonical_name,
            character_id=final_character_id,
            method=result.method,
            confidence=result.confidence,
            blocked_by=result.blocked_by,
        )

        logger.info(
            "reconcile book=%s cluster=%r -> character=%s method=%s blocked=%s",
            book_id,
            cluster.character.canonical_name,
            final_character_id,
            result.method,
            result.blocked_by,
        )

    await repository.recompute_derived_fields(session, touched_character_ids)
    await repository.bump_roster_version(session, project_id)

    return len(clusters)

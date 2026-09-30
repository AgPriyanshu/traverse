from uuid import UUID

from sqlalchemy import delete
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..db.models.relation_model import RelationEvidence
from ..relations import aggregate as aggregation
from ..relations.repository import load_project_facts, replace_project_relations
from . import upsert


async def reaggregate_project(session: SQLModelAsyncSession, project_id: UUID) -> int:
    """Recompute every non-human-verified edge from the evidence Postgres still holds.

    Call after anything that can leave an edge with less evidence than it had
    — a book removal being the motivating case. An edge with no evidence left
    simply does not reappear: :func:`replace_project_relations` only ever
    inserts what :func:`aggregation.aggregate` produces from what is passed in.

    Returns:
        The number of relations written.
    """
    facts = await load_project_facts(session, project_id)
    result = aggregation.aggregate(facts)
    written = await replace_project_relations(session, project_id, result.relations)

    return written


async def remove_book(
    session: SQLModelAsyncSession, project_id: UUID, book_id: UUID
) -> dict[str, int]:
    """Cascade one book's removal through relations and the Neo4j projection.

    Deletes this book's evidence explicitly rather than relying only on the
    ``Book`` row's own ``ON DELETE CASCADE``, so this is safe to call whether
    or not the caller has deleted the ``Book`` row yet. Reaggregates every edge
    from what Postgres still holds afterwards, then re-projects Neo4j so the
    standing graph matches — the same :func:`upsert.upsert_project` an
    ordinary pass-2 run uses, not a bespoke removal projection.

    Args:
        session: An open database session.
        project_id: The project the book belongs to.
        book_id: The book being removed.

    Returns:
        Counts: ``evidence_deleted``, ``relations_written``, plus whatever
        :func:`upsert.upsert_project` reports (``books``, ``characters``,
        ``relations``, ``edges``).

    Raises:
        upsert.EvidenceRequiredError: Should not happen — reaggregation never
            produces an edge without evidence — but is not swallowed if it
            does, since projecting one would be a worse failure than raising.
        upsert.ProjectionMismatchError: If Neo4j ends up with a different edge
            count than Postgres implies, e.g. because a character-side sweep
            this call did not know about has not run yet.
    """
    result = await session.execute(
        delete(RelationEvidence).where(RelationEvidence.book_id == book_id)
    )
    deleted_evidence = result.rowcount or 0
    await session.commit()

    written = await reaggregate_project(session, project_id)
    projected = await upsert.upsert_project(session, project_id)

    return {
        "evidence_deleted": deleted_evidence,
        "relations_written": written,
        **projected,
    }

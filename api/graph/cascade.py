"""Book-removal cascade — the relations/graph side of PRD §12.1b.

Book removal cascades by **evidence**, never by character or by relation: a
book's own ``RelationEvidence`` rows go, any edge left with no evidence
anywhere is dropped, and any edge that still has evidence elsewhere is kept
with its confidence and evidence count recomputed from what remains. This
mirrors the same "recompute the whole project from raw evidence" pattern
``relations.tasks._aggregate_relations`` already uses for an ordinary pass-2
run, which is what makes a removal converge to a consistent graph through the
same recompute rather than a bespoke "subtract one book" code path.

Character-side cleanup — deleting this book's ``CharacterMention``/
``CharacterAppearance`` rows, sweeping a ``Character`` left with zero
appearances, and recomputing its derived fields (``first_book_id``,
``first_chapter``, series-wide tier, mention count) — is be1's S5.3 concern
(``api/extraction/repository.py``), not this module's. The two sides are
order-independent: deleting a ``Character`` row cascades away (``ON DELETE
CASCADE``) every ``Relation`` naming it, so whichever runs first, the other
converges on the same final state. See ``plans/sprint-5/HANDOFF.md`` for the
integration contract with ``DELETE /books/{id}``.
"""

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

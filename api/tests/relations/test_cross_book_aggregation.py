import uuid

import pytest
from sqlalchemy import select

from api.contracts.enums import AssertionType
from api.db.models import Book, Character, Relation, RelationEvidence
from api.db.models.chunk_model import DocumentChunk
from api.relations import aggregate as aggregation
from api.relations.repository import load_project_facts, replace_project_relations


@pytest.mark.asyncio
async def test_relation_established_in_two_books_is_one_edge_with_evidence_from_both(
    session, project, book
):
    """S5.7: aggregation is project-wide, run at each book's aggregate stage.

    Mirrors ``relations.tasks._aggregate_relations``: book one's run writes one
    edge from its own fact; book two's run adds its own fact to book one's
    standing evidence (``load_project_facts``) and reaggregates the whole
    project. The result is one row, not two, with evidence from both books in
    series-position order.
    """
    book2 = Book(
        project_id=project.id,
        title="Book Two",
        content_hash=uuid.uuid4().hex,
        series_order=2,
    )
    session.add(book2)
    sirius = Character(project_id=project.id, canonical_name="Sirius Black")
    harry = Character(project_id=project.id, canonical_name="Harry Potter")
    session.add_all([sirius, harry])
    await session.commit()
    await session.refresh(book2)

    chunk1 = DocumentChunk(
        book_id=book.id,
        text="Sirius is Harry's godfather.",
        pages=[1],
        page_start=1,
        page_end=1,
    )
    chunk2 = DocumentChunk(
        book_id=book2.id,
        text="Sirius, Harry's godfather, smiled.",
        pages=[9],
        page_start=9,
        page_end=9,
    )
    session.add_all([chunk1, chunk2])
    await session.commit()
    await session.refresh(chunk1)
    await session.refresh(chunk2)

    fact_book1 = aggregation.Fact(
        subject_id=sirius.id,
        predicate="guardian_of",
        object_id=harry.id,
        chunk_id=chunk1.id,
        book_id=book.id,
        book_order=1,
        chapter=3,
        page_start=1,
        page_end=1,
        quote="Sirius is Harry's godfather.",
        assertion_type=AssertionType.NARRATED,
        asserted_by_id=None,
        confidence=0.9,
    )
    result1 = aggregation.aggregate([fact_book1])
    await replace_project_relations(session, project.id, result1.relations)

    stored = (
        (
            await session.execute(
                select(Relation).where(Relation.project_id == project.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(stored) == 1
    assert stored[0].evidence_count == 1
    assert stored[0].first_book_order == 1

    fact_book2 = aggregation.Fact(
        subject_id=sirius.id,
        predicate="guardian_of",
        object_id=harry.id,
        chunk_id=chunk2.id,
        book_id=book2.id,
        book_order=2,
        chapter=9,
        page_start=9,
        page_end=9,
        quote="Sirius, Harry's godfather, smiled.",
        assertion_type=AssertionType.NARRATED,
        asserted_by_id=None,
        confidence=0.9,
    )
    earlier = await load_project_facts(session, project.id, exclude_book_id=book2.id)
    result2 = aggregation.aggregate([*earlier, fact_book2])
    await replace_project_relations(session, project.id, result2.relations)

    stored = (
        (
            await session.execute(
                select(Relation).where(Relation.project_id == project.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(stored) == 1
    relation = stored[0]
    assert relation.evidence_count == 2
    assert relation.first_book_order == 1

    evidence = (
        (
            await session.execute(
                select(RelationEvidence)
                .where(RelationEvidence.relation_id == relation.id)
                .order_by(RelationEvidence.book_order)
            )
        )
        .scalars()
        .all()
    )
    assert [item.book_order for item in evidence] == [1, 2]


@pytest.mark.asyncio
async def test_relation_id_is_stable_across_reaggregation_reruns(
    session, project, book
):
    """The same identity-stability invariant Sprint 4 fixed for ``Character``
    (``persist_characters`` upserting by natural key instead of delete/
    reinsert): a rerun that regenerates a relation's id cascade-deletes its
    evidence and orphans any citation, review task or Neo4j edge id pointing
    at the old one. ``replace_project_relations`` must reuse the existing row
    for an unchanged ``(subject, predicate, object)`` key.
    """
    a = Character(project_id=project.id, canonical_name="Anne Shirley")
    b = Character(project_id=project.id, canonical_name="Diana Barry")
    session.add_all([a, b])
    await session.commit()

    chunk = DocumentChunk(
        book_id=book.id,
        text="Anne and Diana are bosom friends.",
        pages=[1],
        page_start=1,
        page_end=1,
    )
    session.add(chunk)
    await session.commit()
    await session.refresh(chunk)

    fact = aggregation.Fact(
        subject_id=a.id,
        predicate="friend_of",
        object_id=b.id,
        chunk_id=chunk.id,
        book_id=book.id,
        book_order=1,
        chapter=1,
        page_start=1,
        page_end=1,
        quote="Anne and Diana are bosom friends.",
        assertion_type=AssertionType.NARRATED,
        asserted_by_id=None,
        confidence=0.9,
    )

    await replace_project_relations(
        session, project.id, aggregation.aggregate([fact]).relations
    )
    first_run = (
        (
            await session.execute(
                select(Relation).where(Relation.project_id == project.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(first_run) == 1
    original_id = first_run[0].id

    # An idempotent rerun over the same fact — nothing about the edge changed.
    await replace_project_relations(
        session, project.id, aggregation.aggregate([fact]).relations
    )
    second_run = (
        (
            await session.execute(
                select(Relation).where(Relation.project_id == project.id)
            )
        )
        .scalars()
        .all()
    )

    assert len(second_run) == 1
    assert second_run[0].id == original_id

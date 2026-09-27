import uuid

import pytest
from sqlalchemy import select

from api.contracts.enums import AssertionType, RelationFamily
from api.db.models import (
    Book,
    Character,
    CharacterAppearance,
    Relation,
    RelationEvidence,
)
from api.db.models.chunk_model import DocumentChunk
from api.graph import cascade, projection, upsert


@pytest.mark.asyncio
async def test_remove_book_drops_book_only_edges_and_keeps_shared_ones(
    session, project
):
    """S5.8: book removal cascades by evidence, never by character or relation.

    A relation with evidence in both books survives with its evidence and
    counts recomputed from what remains; a relation this book alone
    evidenced does not come back once its evidence is gone.
    """
    book1 = Book(
        project_id=project.id,
        title="Book One",
        content_hash=uuid.uuid4().hex,
        series_order=1,
    )
    book2 = Book(
        project_id=project.id,
        title="Book Two",
        content_hash=uuid.uuid4().hex,
        series_order=2,
    )
    session.add_all([book1, book2])

    sirius = Character(project_id=project.id, canonical_name="Sirius Black")
    harry = Character(project_id=project.id, canonical_name="Harry Potter")
    peter = Character(project_id=project.id, canonical_name="Peter Pettigrew")
    session.add_all([sirius, harry, peter])
    await session.commit()
    for row in (book1, book2, sirius, harry, peter):
        await session.refresh(row)

    session.add_all(
        [
            CharacterAppearance(character_id=sirius.id, book_id=book1.id),
            CharacterAppearance(character_id=sirius.id, book_id=book2.id),
            CharacterAppearance(character_id=harry.id, book_id=book1.id),
            CharacterAppearance(character_id=harry.id, book_id=book2.id),
            CharacterAppearance(character_id=peter.id, book_id=book2.id),
        ]
    )
    await session.commit()

    chunk1 = DocumentChunk(
        book_id=book1.id,
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
    chunk3 = DocumentChunk(
        book_id=book2.id,
        text="Sirius chased Peter through the shrieking shack.",
        pages=[20],
        page_start=20,
        page_end=20,
    )
    session.add_all([chunk1, chunk2, chunk3])
    await session.commit()
    for chunk in (chunk1, chunk2, chunk3):
        await session.refresh(chunk)

    shared = Relation(
        project_id=project.id,
        subject_character_id=sirius.id,
        object_character_id=harry.id,
        predicate="guardian_of",
        family=RelationFamily.KINSHIP,
        confidence=0.9,
        evidence_count=2,
        first_book_order=1,
    )
    book2_only = Relation(
        project_id=project.id,
        subject_character_id=sirius.id,
        object_character_id=peter.id,
        predicate="enemy_of",
        family=RelationFamily.ADVERSARIAL,
        confidence=0.6,
        evidence_count=1,
        first_book_order=2,
    )
    session.add_all([shared, book2_only])
    await session.flush()
    session.add_all(
        [
            RelationEvidence(
                relation_id=shared.id,
                book_id=book1.id,
                chunk_id=chunk1.id,
                book_order=1,
                chapter_no=3,
                page_start=1,
                page_end=1,
                quote="Sirius is Harry's godfather.",
                assertion_type=AssertionType.NARRATED,
            ),
            RelationEvidence(
                relation_id=shared.id,
                book_id=book2.id,
                chunk_id=chunk2.id,
                book_order=2,
                chapter_no=9,
                page_start=9,
                page_end=9,
                quote="Sirius, Harry's godfather, smiled.",
                assertion_type=AssertionType.NARRATED,
            ),
            RelationEvidence(
                relation_id=book2_only.id,
                book_id=book2.id,
                chunk_id=chunk3.id,
                book_order=2,
                chapter_no=20,
                page_start=20,
                page_end=20,
                quote="Sirius chased Peter through the shrieking shack.",
                assertion_type=AssertionType.NARRATED,
            ),
        ]
    )
    await session.commit()

    await upsert.upsert_project(session, project.id)

    try:
        counts = await cascade.remove_book(session, project.id, book2.id)

        # Book two contributed one evidence item to the shared relation and
        # one to the book-two-only relation — both are deleted.
        assert counts["evidence_deleted"] == 2
        assert counts["relations_written"] == 1

        remaining = (
            (
                await session.execute(
                    select(Relation).where(Relation.project_id == project.id)
                )
            )
            .scalars()
            .all()
        )
        assert [r.id for r in remaining] == [shared.id]
        assert remaining[0].evidence_count == 1
        assert remaining[0].first_book_order == 1

        evidence = (
            (
                await session.execute(
                    select(RelationEvidence).where(
                        RelationEvidence.relation_id == shared.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(evidence) == 1
        assert evidence[0].book_id == book1.id
    finally:
        await projection.reset_project(project.id)


@pytest.mark.asyncio
async def test_remove_book_is_a_no_op_when_the_book_evidenced_nothing(session, project):
    book = Book(
        project_id=project.id,
        title="Untouched Book",
        content_hash=uuid.uuid4().hex,
        series_order=1,
    )
    session.add(book)
    await session.commit()
    await session.refresh(book)

    try:
        counts = await cascade.remove_book(session, project.id, book.id)

        assert counts["evidence_deleted"] == 0
        assert counts["relations_written"] == 0
    finally:
        await projection.reset_project(project.id)

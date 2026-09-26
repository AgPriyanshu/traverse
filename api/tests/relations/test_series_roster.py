import uuid

import pytest

from api.contracts.enums import ImportanceTier
from api.db.models import Book, Character, CharacterAppearance, CharacterMention
from api.db.models.chunk_model import DocumentChunk
from api.relations.repository import load_project_roster


@pytest.mark.asyncio
async def test_protagonist_and_major_are_project_wide_but_minor_is_book_local(
    session, project, book
):
    """S5.5: a later book always sees the leads; a walk-on stays local."""
    book2 = Book(
        project_id=project.id,
        title="Book Two",
        content_hash=uuid.uuid4().hex,
        series_order=2,
    )
    session.add(book2)
    await session.commit()
    await session.refresh(book2)

    protagonist = Character(
        project_id=project.id,
        canonical_name="Anne Shirley",
        importance_tier=ImportanceTier.PROTAGONIST,
    )
    major = Character(
        project_id=project.id,
        canonical_name="Gilbert Blythe",
        importance_tier=ImportanceTier.MAJOR,
    )
    minor_book_one_only = Character(
        project_id=project.id,
        canonical_name="Mrs Lynde",
        importance_tier=ImportanceTier.MINOR,
    )
    minor_book_two = Character(
        project_id=project.id,
        canonical_name="Davy Keith",
        importance_tier=ImportanceTier.MINOR,
    )
    session.add_all([protagonist, major, minor_book_one_only, minor_book_two])
    await session.commit()

    # Only book one ever saw the protagonist, the major and the book-one-only
    # minor; only book two ever saw the book-two minor.
    session.add_all(
        [
            CharacterAppearance(character_id=protagonist.id, book_id=book.id),
            CharacterAppearance(character_id=major.id, book_id=book.id),
            CharacterAppearance(character_id=minor_book_one_only.id, book_id=book.id),
            CharacterAppearance(character_id=minor_book_two.id, book_id=book2.id),
        ]
    )
    await session.commit()

    roster = await load_project_roster(session, book2.id)
    names = {entry.canonical_name for entry in roster}

    assert names == {"Anne Shirley", "Gilbert Blythe", "Davy Keith"}


@pytest.mark.asyncio
async def test_minor_character_mentioned_without_an_appearance_yet_is_included(
    session, project, book
):
    """A mention this book, even before an appearance record, counts as local."""
    chunk = DocumentChunk(
        book_id=book.id,
        text="A stranger passed through.",
        pages=[1],
        page_start=1,
        page_end=1,
    )
    session.add(chunk)
    mentioned = Character(
        project_id=project.id,
        canonical_name="Passing Stranger",
        importance_tier=ImportanceTier.MENTIONED,
    )
    session.add(mentioned)
    await session.commit()
    await session.refresh(chunk)

    session.add(
        CharacterMention(
            character_id=mentioned.id,
            book_id=book.id,
            chunk_id=chunk.id,
            surface_form="Passing Stranger",
            page=1,
        )
    )
    await session.commit()

    roster = await load_project_roster(session, book.id)

    assert {entry.canonical_name for entry in roster} == {"Passing Stranger"}


@pytest.mark.asyncio
async def test_minor_character_from_a_different_book_is_excluded(
    session, project, book
):
    book2 = Book(
        project_id=project.id,
        title="Book Two",
        content_hash=uuid.uuid4().hex,
        series_order=2,
    )
    session.add(book2)
    minor = Character(
        project_id=project.id,
        canonical_name="Only In Book Two",
        importance_tier=ImportanceTier.MINOR,
    )
    session.add(minor)
    await session.commit()
    await session.refresh(book2)

    session.add(CharacterAppearance(character_id=minor.id, book_id=book2.id))
    await session.commit()

    roster = await load_project_roster(session, book.id)

    assert roster == []


@pytest.mark.asyncio
async def test_unknown_book_returns_an_empty_roster(session):
    roster = await load_project_roster(session, uuid.uuid4())

    assert roster == []

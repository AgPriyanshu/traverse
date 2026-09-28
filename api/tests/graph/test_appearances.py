import uuid

import pytest

from api.contracts.enums import ImportanceTier
from api.db.models import Book, Character, CharacterAppearance
from api.graph.repository import list_appearances
from api.query.scope import ReadingScope


@pytest.mark.asyncio
async def test_appearances_are_series_ordered_and_position_gated(session, project):
    book1 = Book(
        project_id=project.id,
        title="Anne of Green Gables",
        content_hash=uuid.uuid4().hex,
        series_order=1,
    )
    book2 = Book(
        project_id=project.id,
        title="Anne of Avonlea",
        content_hash=uuid.uuid4().hex,
        series_order=2,
    )
    session.add_all([book1, book2])
    await session.commit()
    await session.refresh(book1)
    await session.refresh(book2)

    character = Character(
        project_id=project.id,
        canonical_name="Anne Shirley",
        importance_tier=ImportanceTier.PROTAGONIST,
        first_book_id=book1.id,
        first_chapter=3,
    )
    session.add(character)
    await session.commit()
    await session.refresh(character)

    session.add_all(
        [
            CharacterAppearance(
                character_id=character.id,
                book_id=book2.id,
                first_page=10,
                first_chapter=2,
                mention_count=5,
                importance_tier=ImportanceTier.PROTAGONIST,
                surface_forms=["Miss Shirley"],
            ),
            CharacterAppearance(
                character_id=character.id,
                book_id=book1.id,
                first_page=1,
                first_chapter=3,
                mention_count=20,
                importance_tier=ImportanceTier.PROTAGONIST,
                surface_forms=["Anne Shirley"],
            ),
        ]
    )
    await session.commit()

    appearances = await list_appearances(
        session, character.id, scope=ReadingScope.unlimited()
    )

    assert [a.book_id for a in appearances] == [book1.id, book2.id]
    assert appearances[1].surface_forms == ["Miss Shirley"]

    # A reader still on book one, chapter ten never sees the book-two row.
    limited = await list_appearances(
        session, character.id, scope=ReadingScope(book_order=1, chapter=10)
    )
    assert [a.book_id for a in limited] == [book1.id]


@pytest.mark.asyncio
async def test_character_not_yet_met_is_hidden_entirely(session, project):
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
    await session.commit()
    await session.refresh(book2)

    late_character = Character(
        project_id=project.id,
        canonical_name="Davy Keith",
        first_book_id=book2.id,
        first_chapter=1,
    )
    session.add(late_character)
    await session.commit()

    hidden = await list_appearances(
        session, late_character.id, scope=ReadingScope(book_order=1, chapter=5)
    )

    assert hidden is None


@pytest.mark.asyncio
async def test_unknown_character_returns_none(session):
    hidden_or_missing = await list_appearances(
        session, uuid.uuid4(), scope=ReadingScope.unlimited()
    )
    assert hidden_or_missing is None

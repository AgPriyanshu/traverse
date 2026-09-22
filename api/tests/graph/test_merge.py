import uuid

import pytest
from sqlmodel import select

from api.contracts.enums import ImportanceTier, ResolutionMethod
from api.db.models.character_model import (
    Character,
    CharacterAppearance,
    CharacterMention,
)
from api.db.models.chunk_model import DocumentChunk
from api.db.models.project_model import Book, Chapter, Project
from api.graph import merge
from api.graph.merge import CharacterNotFoundError, MergeValidationError


async def _make_chapter(
    session, book: Book, *, number: int, page_start: int, page_end: int
) -> Chapter:
    chapter = Chapter(
        book_id=book.id, number=number, page_start=page_start, page_end=page_end
    )
    session.add(chapter)
    await session.flush()

    return chapter


async def _make_chunk(
    session, book: Book, chapter: Chapter, *, page: int
) -> DocumentChunk:
    chunk = DocumentChunk(
        book_id=book.id,
        chapter_id=chapter.id,
        text=f"page {page} text",
        pages=[page],
        page_start=page,
        page_end=page,
    )
    session.add(chunk)
    await session.flush()

    return chunk


async def _make_character(
    session, project: Project, name: str, *, tier: ImportanceTier = ImportanceTier.MINOR
) -> Character:
    character = Character(
        project_id=project.id, canonical_name=name, importance_tier=tier
    )
    session.add(character)
    await session.flush()

    return character


async def _make_mention(
    session,
    character: Character,
    book: Book,
    chunk: DocumentChunk,
    *,
    surface_form: str,
    page: int,
) -> CharacterMention:
    mention = CharacterMention(
        character_id=character.id,
        book_id=book.id,
        chunk_id=chunk.id,
        surface_form=surface_form,
        page=page,
        resolution_method=ResolutionMethod.EXACT,
    )
    session.add(mention)
    await session.flush()

    return mention


@pytest.fixture
async def two_chapter_book(
    session, book: Book
) -> tuple[Chapter, Chapter, DocumentChunk, DocumentChunk]:
    chapter_one = await _make_chapter(session, book, number=1, page_start=1, page_end=5)
    chapter_two = await _make_chapter(
        session, book, number=2, page_start=6, page_end=10
    )
    chunk_one = await _make_chunk(session, book, chapter_one, page=2)
    chunk_two = await _make_chunk(session, book, chapter_two, page=8)

    return chapter_one, chapter_two, chunk_one, chunk_two


async def test_merge_combines_mentions_with_zero_orphans(
    session, project, book, two_chapter_book
):
    _chapter_one, _chapter_two, chunk_one, chunk_two = two_chapter_book

    target = await _make_character(session, project, "Catherine Earnshaw")
    source = await _make_character(session, project, "Catherine")
    await session.commit()

    for surface, page in [("Catherine", 1), ("Cathy", 2)]:
        await _make_mention(
            session, target, book, chunk_one, surface_form=surface, page=page
        )
    for surface, page in [("Catherine", 8), ("Miss Earnshaw", 9)]:
        await _make_mention(
            session, source, book, chunk_two, surface_form=surface, page=page
        )
    await session.commit()

    merged = await merge.merge_characters(
        session, source_ids=[source.id], target_id=target.id
    )

    assert merged.id == target.id
    assert merged.mention_count == 4
    assert merged.first_page == 1
    assert merged.first_chapter == 1
    assert sorted(merged.aliases) == ["Catherine", "Cathy", "Miss Earnshaw"]
    assert merged.human_verified is True

    # last_chapter/last_book_id aren't on CharacterOut (contracts/api.py never
    # exposed them), but the recompute must still have set them correctly on
    # the row itself.
    target_row = await session.get(Character, target.id)
    assert target_row.last_chapter == 2

    assert await session.get(Character, source.id) is None

    mentions = (
        await session.exec(
            select(CharacterMention).where(CharacterMention.character_id == target.id)
        )
    ).all()
    assert len(mentions) == 4
    assert {m.character_id for m in mentions} == {target.id}

    orphaned = (
        await session.exec(
            select(CharacterMention).where(CharacterMention.character_id == source.id)
        )
    ).all()
    assert orphaned == []

    appearances = (
        await session.exec(
            select(CharacterAppearance).where(
                CharacterAppearance.character_id == target.id
            )
        )
    ).all()
    assert len(appearances) == 1
    assert appearances[0].mention_count == 4
    assert sorted(appearances[0].surface_forms) == [
        "Catherine",
        "Cathy",
        "Miss Earnshaw",
    ]


async def test_merge_rejects_target_in_sources(session, project):
    target = await _make_character(session, project, "A")
    await session.commit()

    with pytest.raises(MergeValidationError):
        await merge.merge_characters(
            session, source_ids=[target.id], target_id=target.id
        )


async def test_merge_rejects_unknown_character(session, project):
    target = await _make_character(session, project, "A")
    await session.commit()

    with pytest.raises(CharacterNotFoundError):
        await merge.merge_characters(
            session, source_ids=[uuid.uuid4()], target_id=target.id
        )


async def test_merge_then_split_restores_original_partition(
    session, project, book, two_chapter_book
):
    _chapter_one, _chapter_two, chunk_one, chunk_two = two_chapter_book

    target = await _make_character(session, project, "Catherine Earnshaw")
    source = await _make_character(session, project, "Catherine Linton")
    await session.commit()

    target_mentions = [
        await _make_mention(
            session, target, book, chunk_one, surface_form="Catherine", page=1
        ),
        await _make_mention(
            session, target, book, chunk_one, surface_form="Cathy", page=2
        ),
    ]
    source_mentions = [
        await _make_mention(
            session, source, book, chunk_two, surface_form="Catherine", page=8
        ),
        await _make_mention(
            session, source, book, chunk_two, surface_form="young Catherine", page=9
        ),
    ]
    await session.commit()

    await merge.merge_characters(session, source_ids=[source.id], target_id=target.id)

    split = await merge.split_character(
        session,
        character_id=target.id,
        mention_ids=[m.id for m in source_mentions],
        new_canonical_name="Catherine Linton",
    )
    restored_source, restored_new = split

    assert restored_source.mention_count == len(target_mentions)
    assert restored_source.first_page == 1
    assert restored_source.first_chapter == 1

    assert restored_new.mention_count == len(source_mentions)
    assert restored_new.first_page == 8
    assert restored_new.first_chapter == 2
    assert restored_new.canonical_name == "Catherine Linton"


async def test_split_rejects_every_mention_named(
    session, project, book, two_chapter_book
):
    _chapter_one, _chapter_two, chunk_one, _chunk_two = two_chapter_book
    source = await _make_character(session, project, "Elizabeth")
    await session.commit()
    mention = await _make_mention(
        session, source, book, chunk_one, surface_form="Elizabeth", page=1
    )
    await session.commit()

    with pytest.raises(MergeValidationError):
        await merge.split_character(
            session,
            character_id=source.id,
            mention_ids=[mention.id],
            new_canonical_name="Someone Else",
        )


async def test_split_rejects_mention_from_another_character(
    session, project, book, two_chapter_book
):
    _chapter_one, _chapter_two, chunk_one, _chunk_two = two_chapter_book
    source = await _make_character(session, project, "Elizabeth")
    other = await _make_character(session, project, "Jane")
    await session.commit()
    await _make_mention(
        session, source, book, chunk_one, surface_form="Elizabeth", page=1
    )
    await _make_mention(session, source, book, chunk_one, surface_form="Lizzy", page=2)
    foreign_mention = await _make_mention(
        session, other, book, chunk_one, surface_form="Jane", page=1
    )
    await session.commit()

    with pytest.raises(MergeValidationError):
        await merge.split_character(
            session,
            character_id=source.id,
            mention_ids=[foreign_mention.id],
            new_canonical_name="Someone Else",
        )

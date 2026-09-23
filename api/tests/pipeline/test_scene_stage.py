from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import ResolutionMethod
from api.db.engine import engine
from api.db.models import (
    Book,
    Character,
    CharacterAppearance,
    CharacterMention,
    DocumentChunk,
)
from api.pipeline import prefilter, scene_repository, scene_stage

# Mirrors the shapes requested in plans/sprint-4/SCR.md SCR-1. Replace with the
# migrated tables once they land; IF NOT EXISTS keeps this harmless afterwards.
_DDL = (
    "CREATE TABLE IF NOT EXISTS scene (id uuid PRIMARY KEY, "
    "book_id uuid NOT NULL REFERENCES book(id) ON DELETE CASCADE, "
    "chapter_id uuid, position int NOT NULL, page_start int NOT NULL, "
    "page_end int NOT NULL, chunk_ids uuid[] NOT NULL)",
    "CREATE TABLE IF NOT EXISTS scene_participant (scene_id uuid NOT NULL "
    "REFERENCES scene(id) ON DELETE CASCADE, character_id uuid NOT NULL "
    "REFERENCES character(id) ON DELETE CASCADE, mention_count int NOT NULL, "
    "PRIMARY KEY (scene_id, character_id))",
    "CREATE TABLE IF NOT EXISTS dialogue_line (id uuid PRIMARY KEY "
    "DEFAULT gen_random_uuid(), book_id uuid NOT NULL REFERENCES book(id) "
    "ON DELETE CASCADE, chunk_id uuid NOT NULL REFERENCES documentchunk(id) "
    "ON DELETE CASCADE, char_start int NOT NULL, char_end int NOT NULL, "
    "speaker_character_id uuid REFERENCES character(id) ON DELETE SET NULL, "
    "method text NOT NULL, confidence float NOT NULL)",
)


@pytest_asyncio.fixture
async def scene_tables() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        for statement in _DDL:
            await conn.execute(text(statement))

    yield

    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE dialogue_line, scene_participant, scene CASCADE")
        )


async def _character(session: SQLModelAsyncSession, book: Book, name: str) -> Character:
    character = Character(
        project_id=book.project_id, canonical_name=name, aliases=[name.split()[0]]
    )
    session.add(character)
    await session.flush()
    session.add(CharacterAppearance(character_id=character.id, book_id=book.id))

    return character


async def _chunk(
    session: SQLModelAsyncSession,
    book: Book,
    body: str,
    page: int,
    *,
    who: list[Character],
) -> DocumentChunk:
    chunk = DocumentChunk(
        book_id=book.id, text=body, pages=[page], page_start=page, page_end=page
    )
    session.add(chunk)
    await session.flush()
    for character in who:
        session.add(
            CharacterMention(
                character_id=character.id,
                book_id=book.id,
                chunk_id=chunk.id,
                surface_form=character.canonical_name.split()[0],
                page=page,
                resolution_method=ResolutionMethod.EXACT,
            )
        )

    return chunk


@pytest_asyncio.fixture
async def seeded(session: SQLModelAsyncSession, book: Book, scene_tables: None):
    elizabeth = await _character(session, book, "Elizabeth Bennet")
    darcy = await _character(session, book, "Fitzwilliam Darcy")
    jane = await _character(session, book, "Jane Bennet")
    chunks = [
        await _chunk(
            session,
            book,
            '"Do you dance?" said Elizabeth.\n"Never."',
            1,
            who=[elizabeth],
        ),
        await _chunk(session, book, "The rain fell on the moor.", 1, who=[]),
        await _chunk(session, book, "Nothing happened at all.", 2, who=[]),
        await _chunk(
            session,
            book,
            "Jane wrote to Elizabeth about Darcy.",
            3,
            who=[jane, elizabeth],
        ),
        await _chunk(session, book, "Darcy walked out alone.", 3, who=[darcy]),
    ]
    await session.commit()

    return elizabeth, darcy, jane, chunks


async def test_stage_persists_scenes_participants_and_speakers(
    session: SQLModelAsyncSession, book: Book, seeded
) -> None:
    elizabeth, darcy, _, chunks = seeded

    result = await scene_stage.build_scenes_and_speakers(
        session, book.id, use_llm=False
    )

    scenes = await scene_repository.list_scenes(session, book.id)
    lines = await scene_repository.list_dialogue_lines(session, book.id)
    assert result is not None and result.scenes == len(scenes)
    assert sorted(c for s in scenes for c in s.chunk_ids) == sorted(
        c.id for c in chunks
    )
    assert [line.speaker_character_id for line in lines][0] == elizabeth.id
    assert lines[0].method == "explicit_tag"
    assert None not in {line.chunk_id for line in lines}


async def test_stage_is_idempotent(
    session: SQLModelAsyncSession, book: Book, seeded
) -> None:
    await scene_stage.build_scenes_and_speakers(session, book.id, use_llm=False)
    await scene_stage.build_scenes_and_speakers(session, book.id, use_llm=False)

    scenes = await scene_repository.list_scenes(session, book.id)
    lines = await scene_repository.list_dialogue_lines(session, book.id)

    assert len(lines) == 2
    assert len({s.id for s in scenes}) == len(scenes)


async def test_co_presence_lists_scene_mates(
    session: SQLModelAsyncSession, book: Book, seeded
) -> None:
    elizabeth, _, jane, _ = seeded
    await scene_stage.build_scenes_and_speakers(session, book.id, use_llm=False)

    mates = await scene_repository.characters_sharing_scene(
        session, elizabeth.id, book_id=book.id
    )

    assert jane.id in {character_id for character_id, _ in mates}
    assert elizabeth.id not in {character_id for character_id, _ in mates}


async def test_prefilter_keeps_two_mention_chunks_and_thin_scene_chunks(
    session: SQLModelAsyncSession, book: Book, seeded
) -> None:
    _, _, _, chunks = seeded
    await scene_stage.build_scenes_and_speakers(session, book.id, use_llm=False)

    kept = {ref.chunk_id for ref in await prefilter.pass2_candidates(book.id)}

    assert chunks[3].id in kept
    assert chunks[1].id not in kept
    assert chunks[2].id not in kept


async def test_prefilter_reports_reduction(
    session: SQLModelAsyncSession, book: Book, seeded
) -> None:
    await scene_stage.build_scenes_and_speakers(session, book.id, use_llm=False)

    stats = await prefilter.prefilter_stats(book.id)

    assert stats.total_chunks == 5
    assert 0 < stats.reduction_ratio < 1
    assert stats.candidates + round(stats.reduction_ratio * 5) == 5


async def test_stage_skips_quietly_without_the_tables(
    session: SQLModelAsyncSession, book: Book, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def missing(_: SQLModelAsyncSession) -> bool:
        return False

    monkeypatch.setattr(scene_repository, "scene_tables_exist", missing)

    assert await scene_stage.build_scenes_and_speakers(session, book.id) is None

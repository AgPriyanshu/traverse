from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from .scenes import SceneDraft

INSERT_BATCH = 500


@dataclass(frozen=True)
class DialogueLineRow:
    chunk_id: UUID
    char_start: int
    char_end: int
    speaker_character_id: UUID | None
    method: str
    confidence: float


@dataclass(frozen=True)
class SceneRow:
    id: UUID
    chapter_id: UUID | None
    page_start: int
    page_end: int
    chunk_ids: list[UUID]
    participants: dict[UUID, int]


@dataclass(frozen=True)
class CharacterFormsRow:
    character_id: UUID
    canonical_name: str
    forms: list[str]


async def scene_tables_exist(session: SQLModelAsyncSession) -> bool:
    """Whether the scene, participant and dialogue tables have been migrated in."""
    result = await session.execute(
        text(
            "SELECT to_regclass('scene') IS NOT NULL "
            "AND to_regclass('scene_participant') IS NOT NULL "
            "AND to_regclass('dialogue_line') IS NOT NULL"
        )
    )
    exist = bool(result.scalar())

    return exist


async def delete_book_scenes(session: SQLModelAsyncSession, book_id: UUID) -> None:
    """Drop a book's scenes, participants and dialogue lines before a rebuild."""
    await session.execute(
        text("DELETE FROM dialogue_line WHERE book_id = :book_id"),
        {"book_id": book_id},
    )
    await session.execute(
        text("DELETE FROM scene WHERE book_id = :book_id"), {"book_id": book_id}
    )
    await session.commit()


async def insert_scenes(
    session: SQLModelAsyncSession, book_id: UUID, drafts: list[SceneDraft]
) -> dict[int, UUID]:
    """Insert scenes and their participants in bulk.

    Args:
        session: Open session; this function commits.
        book_id: Book the scenes belong to.
        drafts: Scenes in document order.

    Returns:
        Scene id by the draft's index in ``drafts``.
    """
    ids = {index: uuid4() for index in range(len(drafts))}

    scene_rows = [
        {
            "id": ids[index],
            "book_id": book_id,
            "chapter_id": draft.chapter_id,
            "position": index,
            "page_start": draft.page_start,
            "page_end": draft.page_end,
            "chunk_ids": draft.chunk_ids,
        }
        for index, draft in enumerate(drafts)
    ]
    participant_rows = [
        {"scene_id": ids[index], "character_id": character_id, "mention_count": count}
        for index, draft in enumerate(drafts)
        for character_id, count in draft.participants.items()
    ]

    scene_sql = text(
        "INSERT INTO scene (id, book_id, chapter_id, position, page_start, "
        "page_end, chunk_ids) VALUES (:id, :book_id, :chapter_id, :position, "
        ":page_start, :page_end, :chunk_ids)"
    )
    participant_sql = text(
        "INSERT INTO scene_participant (scene_id, character_id, mention_count) "
        "VALUES (:scene_id, :character_id, :mention_count)"
    )

    for start in range(0, len(scene_rows), INSERT_BATCH):
        await session.execute(scene_sql, scene_rows[start : start + INSERT_BATCH])

    for start in range(0, len(participant_rows), INSERT_BATCH):
        await session.execute(
            participant_sql, participant_rows[start : start + INSERT_BATCH]
        )

    await session.commit()

    return ids


async def insert_dialogue_lines(
    session: SQLModelAsyncSession, book_id: UUID, lines: list[DialogueLineRow]
) -> int:
    """Insert dialogue lines in bulk; an unresolved speaker is stored as NULL."""
    rows = [
        {
            "book_id": book_id,
            "chunk_id": line.chunk_id,
            "char_start": line.char_start,
            "char_end": line.char_end,
            "speaker_character_id": line.speaker_character_id,
            "method": line.method,
            "confidence": line.confidence,
        }
        for line in lines
    ]
    statement = text(
        "INSERT INTO dialogue_line (book_id, chunk_id, char_start, char_end, "
        "speaker_character_id, method, confidence) VALUES (:book_id, :chunk_id, "
        ":char_start, :char_end, :speaker_character_id, :method, :confidence)"
    )

    for start in range(0, len(rows), INSERT_BATCH):
        await session.execute(statement, rows[start : start + INSERT_BATCH])

    await session.commit()

    return len(rows)


async def chunk_characters(
    session: SQLModelAsyncSession, book_id: UUID
) -> dict[UUID, dict[UUID, int]]:
    """Return characters mentioned per chunk, with each one's mention count."""
    result = await session.execute(
        text(
            "SELECT chunk_id, character_id, count(*) AS mentions "
            "FROM charactermention WHERE book_id = :book_id "
            "GROUP BY chunk_id, character_id"
        ),
        {"book_id": book_id},
    )
    per_chunk: dict[UUID, dict[UUID, int]] = {}
    for chunk_id, character_id, mentions in result.all():
        per_chunk.setdefault(chunk_id, {})[character_id] = mentions

    return per_chunk


async def character_forms(
    session: SQLModelAsyncSession, book_id: UUID
) -> list[CharacterFormsRow]:
    """Return every surface form each of this book's characters is known by."""
    result = await session.execute(
        text(
            "SELECT c.id, c.canonical_name, "
            "coalesce(array_agg(DISTINCT m.surface_form) "
            "FILTER (WHERE m.surface_form IS NOT NULL), '{}') AS mention_forms, "
            "c.aliases FROM character c "
            "JOIN characterappearance a ON a.character_id = c.id "
            "LEFT JOIN charactermention m ON m.character_id = c.id "
            "AND m.book_id = a.book_id "
            "WHERE a.book_id = :book_id GROUP BY c.id"
        ),
        {"book_id": book_id},
    )
    rows = [
        CharacterFormsRow(
            character_id=character_id,
            canonical_name=canonical_name,
            forms=sorted({canonical_name, *mention_forms, *(aliases or [])}),
        )
        for character_id, canonical_name, mention_forms, aliases in result.all()
    ]

    return rows


async def characters_sharing_scene(
    session: SQLModelAsyncSession, character_id: UUID, *, book_id: UUID | None = None
) -> list[tuple[UUID, int]]:
    """Return characters who share at least one scene with ``character_id``.

    Args:
        session: Open session.
        character_id: The character to look around.
        book_id: Restrict to one book's scenes; ``None`` spans the project.

    Returns:
        ``(character_id, shared_scene_count)``, most co-present first.
    """
    result = await session.execute(
        text(
            "SELECT other.character_id, count(DISTINCT other.scene_id) AS shared "
            "FROM scene_participant me "
            "JOIN scene_participant other ON other.scene_id = me.scene_id "
            "AND other.character_id <> me.character_id "
            "JOIN scene s ON s.id = me.scene_id "
            "WHERE me.character_id = :character_id "
            "AND (CAST(:book_id AS uuid) IS NULL OR s.book_id = :book_id) "
            "GROUP BY other.character_id ORDER BY shared DESC"
        ),
        {"character_id": character_id, "book_id": book_id},
    )
    rows = [(row[0], row[1]) for row in result.all()]

    return rows


async def list_scenes(session: SQLModelAsyncSession, book_id: UUID) -> list[SceneRow]:
    """Return a book's scenes in document order with their participants."""
    scenes = await session.execute(
        text(
            "SELECT id, chapter_id, page_start, page_end, chunk_ids FROM scene "
            "WHERE book_id = :book_id ORDER BY position"
        ),
        {"book_id": book_id},
    )
    participants = await session.execute(
        text(
            "SELECT p.scene_id, p.character_id, p.mention_count "
            "FROM scene_participant p JOIN scene s ON s.id = p.scene_id "
            "WHERE s.book_id = :book_id"
        ),
        {"book_id": book_id},
    )
    by_scene: dict[UUID, dict[UUID, int]] = {}
    for scene_id, character_id, count in participants.all():
        by_scene.setdefault(scene_id, {})[character_id] = count

    rows = [
        SceneRow(
            id=scene_id,
            chapter_id=chapter_id,
            page_start=page_start,
            page_end=page_end,
            chunk_ids=list(chunk_ids),
            participants=by_scene.get(scene_id, {}),
        )
        for scene_id, chapter_id, page_start, page_end, chunk_ids in scenes.all()
    ]

    return rows


async def list_dialogue_lines(
    session: SQLModelAsyncSession, book_id: UUID, *, chunk_id: UUID | None = None
) -> list[DialogueLineRow]:
    """Return a book's dialogue lines, optionally for one chunk."""
    result = await session.execute(
        text(
            "SELECT chunk_id, char_start, char_end, speaker_character_id, method, "
            "confidence FROM dialogue_line WHERE book_id = :book_id "
            "AND (CAST(:chunk_id AS uuid) IS NULL OR chunk_id = :chunk_id) "
            "ORDER BY chunk_id, char_start"
        ),
        {"book_id": book_id, "chunk_id": chunk_id},
    )
    rows = [DialogueLineRow(*row) for row in result.all()]

    return rows

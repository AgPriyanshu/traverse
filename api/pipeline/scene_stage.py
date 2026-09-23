import logging
from collections import Counter
from dataclasses import dataclass
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from . import repository, scene_repository, speakers
from .scenes import SceneChunk, segment_scenes

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SceneStageResult:
    scenes: int
    dialogue_lines: int
    by_method: dict[str, int]
    mean_chunks_per_scene: float


async def build_scenes_and_speakers(
    session: SQLModelAsyncSession, book_id: UUID, *, use_llm: bool = True
) -> SceneStageResult | None:
    """Segment a book into scenes, then attribute every dialogue line in them.

    Runs after the roster is persisted, because scene participants are resolved
    characters and speaker matching needs each character's surface forms.
    Idempotent: a re-run replaces this book's scenes and dialogue lines.

    Args:
        session: Open session; the repository calls commit.
        book_id: Book whose roster has already been persisted.
        use_llm: Whether unresolved lines go to the LLM fallback.

    Returns:
        Counts, including the per-method breakdown of attributed lines, or
        ``None`` when the scene tables have not been migrated in yet.
    """
    if not await scene_repository.scene_tables_exist(session):
        logger.warning(
            "book %s: scene tables are not migrated in (SCR-1); "
            "skipping scenes and speakers",
            book_id,
        )

        return None

    chunk_rows = await repository.list_chunks_with_chapter_number(session, book_id)
    per_chunk = await scene_repository.chunk_characters(session, book_id)
    forms = await scene_repository.character_forms(session, book_id)

    chunks = [
        SceneChunk(
            chunk_id=chunk.id,
            chapter_id=chunk.chapter_id,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            text=chunk.text,
            characters=Counter(per_chunk.get(chunk.id, {})),
        )
        for chunk, _ in chunk_rows
    ]
    drafts = segment_scenes(chunks)

    await scene_repository.delete_book_scenes(session, book_id)
    await scene_repository.insert_scenes(session, book_id, drafts)

    forms_by_character = {row.character_id: row.forms for row in forms}
    names = {row.character_id: row.canonical_name for row in forms}
    chunk_texts = {chunk.id: chunk.text for chunk, _ in chunk_rows}

    work = []
    for draft in drafts:
        matchers = {
            chunk_id: speakers.build_matcher(
                {
                    character_id: forms_by_character.get(character_id, [])
                    for character_id in per_chunk.get(chunk_id, {})
                }
            )
            for chunk_id in draft.chunk_ids
        }
        scene = speakers.SceneText(
            chunk_ids=draft.chunk_ids,
            chunk_texts={
                chunk_id: chunk_texts[chunk_id] for chunk_id in draft.chunk_ids
            },
            participants=dict(draft.participants),
        )
        paragraphs, lines = speakers.attribute_scene(scene, matchers)
        work.append((scene, paragraphs, lines))

    if use_llm:
        await speakers.resolve_with_llm(work, names, book_id=book_id)

    all_lines = [line for _, _, lines in work for line in lines]
    rows = speakers.to_rows(all_lines)
    await scene_repository.insert_dialogue_lines(session, book_id, rows)

    by_method = Counter(row.method for row in rows)
    mean_chunks = len(chunks) / len(drafts) if drafts else 0.0
    result = SceneStageResult(
        scenes=len(drafts),
        dialogue_lines=len(rows),
        by_method=dict(by_method),
        mean_chunks_per_scene=mean_chunks,
    )
    logger.info(
        "book %s: %d scenes (%.1f chunks each), %d dialogue lines %s",
        book_id,
        result.scenes,
        result.mean_chunks_per_scene,
        result.dialogue_lines,
        result.by_method,
    )

    return result

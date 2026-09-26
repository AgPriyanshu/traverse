import logging
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..db.models import DocumentChunk
from . import repository
from .scenes import MIN_SCENE_MENTIONS, build_reading_chunks

logger = logging.getLogger(__name__)


async def candidate_chunk_ids(
    session: SQLModelAsyncSession, book_id: UUID
) -> tuple[set[UUID], str]:
    """Return the chunk ids pass 2 should read, and which source decided.

    Prefers be1's prefilter (``api.pipeline.prefilter.pass2_candidates``, S4.10),
    which also keeps single-mention chunks whose scene has two participants.
    Falls back to the same distinct-character rule computed locally from
    ``CharacterMention`` when be1's module is not in this checkout.

    Returns:
        ``(chunk ids, source)`` where source is ``"be1"`` or ``"local"``.
    """
    try:
        from ..pipeline.prefilter import pass2_candidates
    except ImportError:
        logger.warning("api.pipeline.prefilter is absent; using the local prefilter")
        ids = await repository.chunks_with_two_characters(session, book_id)

        return ids, "local"

    refs = await pass2_candidates(book_id, session=session)
    ids = {ref.chunk_id for ref in refs}

    return ids, "be1"


async def candidate_reading_chunks(
    session: SQLModelAsyncSession,
    book_id: UUID,
    chunks: list[tuple[DocumentChunk, int | None]],
) -> tuple[
    list[tuple[DocumentChunk, int | None]],
    set[UUID],
    str,
    dict[UUID, tuple[UUID, ...]],
]:
    """Return the book re-expressed at reading-unit granularity, and which to read.

    Sprint 4's recall audit (real run on Pride and Prejudice, 719 chunks,
    median length 60 characters) found the chunk-level prefilter drops a
    chunk outright whenever its own mention count is 0, even when the chunk's
    *scene* clearly names two or more roster characters elsewhere -- 48 such
    chunks on that book, each a pronoun-only clause ("he had the means of
    exercising it") mid a real scene. Grouping by scene before filtering, and
    reading the whole scene's text as one unit rather than one isolated
    clause, recovers those chunks and gives both the extractor and the
    validator enough context to resolve the pronoun.

    Falls back entirely to the old chunk-level candidate set (``chunks``
    unmodified) when ``api.pipeline.scene_repository`` is absent or the scene
    tables have not been migrated in -- unit tests and any book ingested
    before S4.8 landed still work exactly as before.

    Returns:
        ``(units, keep_ids, source, members)`` -- the whole book at
        reading-unit granularity, the subset of unit ids pass 2 should
        actually read, which source decided (``"be2_scene"``, ``"be1"`` or
        ``"local"``), and a map from each unit's id to the raw chunk ids it
        merges (singleton tuples when the source is not ``"be2_scene"``).
    """
    try:
        from ..pipeline.scene_repository import list_scenes, scene_tables_exist
    except ImportError:
        ids, source = await candidate_chunk_ids(session, book_id)

        return chunks, ids, source, {c.id: (c.id,) for c, _ in chunks}

    if not await scene_tables_exist(session):
        ids, source = await candidate_chunk_ids(session, book_id)

        return chunks, ids, source, {c.id: (c.id,) for c, _ in chunks}

    scenes = await list_scenes(session, book_id)
    units, mentions, members = build_reading_chunks(chunks, scenes)
    orphan_ids: set[UUID] = set()
    if any(count == -1 for count in mentions.values()):
        orphan_ids, _ = await candidate_chunk_ids(session, book_id)

    keep_ids = {
        unit.id
        for unit, _ in units
        if mentions.get(unit.id, -1) >= MIN_SCENE_MENTIONS
        or (mentions.get(unit.id, -1) == -1 and unit.id in orphan_ids)
    }

    return units, keep_ids, "be2_scene", members

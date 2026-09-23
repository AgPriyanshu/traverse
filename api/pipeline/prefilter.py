from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..db.engine import db_session

DEFAULT_MIN_ROSTER_MENTIONS = 2


@dataclass(frozen=True)
class ChunkRef:
    chunk_id: UUID
    scene_id: UUID | None
    chapter_id: UUID | None
    page_start: int
    page_end: int
    roster_mentions: int


@dataclass(frozen=True)
class PrefilterStats:
    total_chunks: int
    candidates: int
    reduction_ratio: float


_CANDIDATES_SQL = text(
    """
    WITH per_chunk AS (
        SELECT c.id AS chunk_id, c.chapter_id, c.page_start, c.page_end,
               count(DISTINCT m.character_id) AS roster_mentions
        FROM documentchunk c
        LEFT JOIN charactermention m ON m.chunk_id = c.id
        WHERE c.book_id = :book_id
        GROUP BY c.id
    ),
    chunk_scene AS (
        SELECT DISTINCT ON (u.chunk_id) u.chunk_id, s.id AS scene_id,
               (SELECT count(*) FROM scene_participant p
                WHERE p.scene_id = s.id) AS scene_participants
        FROM scene s, unnest(s.chunk_ids) AS u(chunk_id)
        WHERE s.book_id = :book_id
        ORDER BY u.chunk_id, s.position
    )
    SELECT pc.chunk_id, cs.scene_id, pc.chapter_id, pc.page_start, pc.page_end,
           pc.roster_mentions,
           (pc.roster_mentions >= :minimum
            OR (pc.roster_mentions >= 1 AND coalesce(cs.scene_participants, 0) >= 2))
           AS keep
    FROM per_chunk pc LEFT JOIN chunk_scene cs ON cs.chunk_id = pc.chunk_id
    ORDER BY pc.page_start, pc.chunk_id
    """
)


async def _classify(
    session: SQLModelAsyncSession, book_id: UUID, minimum: int
) -> list[tuple[ChunkRef, bool]]:
    result = await session.execute(
        _CANDIDATES_SQL, {"book_id": book_id, "minimum": minimum}
    )
    rows = [
        (
            ChunkRef(
                chunk_id=chunk_id,
                scene_id=scene_id,
                chapter_id=chapter_id,
                page_start=page_start,
                page_end=page_end,
                roster_mentions=roster_mentions,
            ),
            keep,
        )
        for (
            chunk_id,
            scene_id,
            chapter_id,
            page_start,
            page_end,
            roster_mentions,
            keep,
        ) in result.all()
    ]

    return rows


async def pass2_candidates(
    book_id: UUID,
    *,
    min_roster_mentions: int = DEFAULT_MIN_ROSTER_MENTIONS,
    session: SQLModelAsyncSession | None = None,
) -> list[ChunkRef]:
    """Return the chunks worth an expensive pass-2 relation call.

    A chunk qualifies when it mentions at least ``min_roster_mentions``
    distinct roster characters, or mentions one while its scene has two or
    more participants: "she refused him" carries a relation and names nobody.
    Counting distinct characters rather than raw mentions is deliberate, since
    one person named three times cannot form a character-character relation.

    Args:
        book_id: Book whose roster and scenes are already persisted.
        min_roster_mentions: Distinct roster characters a chunk needs on its
            own; ``1`` keeps every chunk that names anyone.
        session: Reuse an open session; one is opened when omitted.

    Returns:
        Qualifying chunks in document order, each with its scene id.
    """
    if session is not None:
        rows = await _classify(session, book_id, min_roster_mentions)
    else:
        async with db_session() as owned:
            rows = await _classify(owned, book_id, min_roster_mentions)

    candidates = [ref for ref, keep in rows if keep]

    return candidates


async def prefilter_stats(
    book_id: UUID,
    *,
    min_roster_mentions: int = DEFAULT_MIN_ROSTER_MENTIONS,
    session: SQLModelAsyncSession | None = None,
) -> PrefilterStats:
    """Measure how much of a book never reaches pass 2.

    Returns:
        Total chunks, candidate chunks, and the fraction filtered out.
    """
    if session is not None:
        rows = await _classify(session, book_id, min_roster_mentions)
    else:
        async with db_session() as owned:
            rows = await _classify(owned, book_id, min_roster_mentions)

    kept = sum(1 for _, keep in rows if keep)
    ratio = 1 - kept / len(rows) if rows else 0.0
    stats = PrefilterStats(len(rows), kept, ratio)

    return stats

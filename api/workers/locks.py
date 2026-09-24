from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text

from ..db.engine import engine


@asynccontextmanager
async def book_roster_lock(book_id: UUID) -> AsyncIterator[None]:
    """Serialise the stages that rewrite one book's candidates and roster.

    ``extract_characters`` and ``resolve_aliases`` both replace rows the other
    reads. Two runs of either (a reprocess while the previous run is still
    going, a worker restart that redelivers the task) would otherwise delete
    each other's rows mid-flight. A session-level advisory lock on a dedicated
    connection makes the second run wait, then start from a fresh read.

    Args:
        book_id: Book whose roster stages are about to run.
    """
    key = f"roster:{book_id}"

    async with engine.connect() as connection:
        await connection.execute(
            text("SELECT pg_advisory_lock(hashtextextended(:key, 0))"), {"key": key}
        )
        try:
            yield
        finally:
            await connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                {"key": key},
            )

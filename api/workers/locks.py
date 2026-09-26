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


@asynccontextmanager
async def project_roster_lock(project_id: UUID) -> AsyncIterator[None]:
    """Serialise ``pipeline.reconcile_characters`` across one project's books.

    Two books of the same series reconciling concurrently would both read the
    roster before either writes a merge, and both create a duplicate character
    for the same person — a race that only shows up under load, never in a
    single-book test. A distinct advisory-lock key from ``book_roster_lock``
    keeps the two locks from contending with each other.

    Args:
        project_id: Project whose roster is about to be reconciled.
    """
    key = f"project-roster:{project_id}"

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

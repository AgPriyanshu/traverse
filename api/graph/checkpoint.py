from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from ..config import settings

# psycopg wants a plain libpq URL; SQLAlchemy's driver suffix is not part of
# one and psycopg refuses it outright.
_SQLALCHEMY_DRIVER_SUFFIXES = ("+psycopg", "+psycopg2", "+asyncpg")

CONNECTION_KWARGS = {"autocommit": True, "prepare_threshold": 0, "row_factory": None}


def connection_string() -> str:
    """Return the checkpointer's libpq URL, derived from the app's database URL.

    The checkpointer shares the application database on purpose: a review task
    row and the paused run it belongs to must commit or roll back together.

    Returns:
        ``postgresql://…`` with any SQLAlchemy driver suffix removed.
    """
    dsn = settings.postgres_db_string
    for suffix in _SQLALCHEMY_DRIVER_SUFFIXES:
        dsn = dsn.replace(suffix, "", 1)

    return dsn


@asynccontextmanager
async def checkpointer(*, setup: bool = False) -> AsyncIterator[AsyncPostgresSaver]:
    """Yield an ``AsyncPostgresSaver`` bound to the application database.

    Args:
        setup: Run the checkpointer's own schema migration first. Idempotent,
            but it takes table locks, so leave it off on the hot path and call
            ``setup_checkpointer`` once at deploy time instead.

    Yields:
        A saver ready to pass as a graph's ``checkpointer``.
    """
    async with AsyncPostgresSaver.from_conn_string(connection_string()) as saver:
        if setup:
            await saver.setup()

        yield saver


async def setup_checkpointer() -> None:
    """Create the checkpointer tables. Idempotent; run once per environment."""
    async with checkpointer(setup=True):
        pass

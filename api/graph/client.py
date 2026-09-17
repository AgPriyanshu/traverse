import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from ..config import settings

logger = logging.getLogger(__name__)

_driver: AsyncDriver | None = None
_driver_lock = asyncio.Lock()

# Neo4j accepts Bolt connections roughly 20s after the container starts, and
# every agent hits that window at least once. Back off rather than fail the
# whole process startup.
_CONNECT_ATTEMPTS = 8
_CONNECT_BACKOFF_SECONDS = 1.5
_CONNECT_BACKOFF_CAP_SECONDS = 15.0

SCHEMA_STATEMENTS: tuple[str, ...] = (
    "CREATE CONSTRAINT character_id IF NOT EXISTS "
    "FOR (c:Character) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT book_id IF NOT EXISTS FOR (b:Book) REQUIRE b.id IS UNIQUE",
    "CREATE INDEX character_book IF NOT EXISTS FOR (c:Character) ON (c.book_id)",
    "CREATE INDEX character_project IF NOT EXISTS FOR (c:Character) ON (c.project_id)",
    "CREATE INDEX character_name IF NOT EXISTS FOR (c:Character) ON (c.canonical_name)",
    "CREATE INDEX rel_predicate IF NOT EXISTS FOR ()-[r:RELATED]-() ON (r.predicate)",
    "CREATE INDEX rel_chapter IF NOT EXISTS FOR ()-[r:RELATED]-() ON (r.first_chapter)",
)


def _build_driver() -> AsyncDriver:
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        max_connection_pool_size=50,
    )

    return driver


async def _verify_with_backoff(driver: AsyncDriver) -> None:
    """Wait for the server to accept connections, with exponential backoff.

    Raises:
        ServiceUnavailable: If the server is still unreachable after every
            attempt.
    """
    delay = _CONNECT_BACKOFF_SECONDS
    last_error: ServiceUnavailable | None = None

    for attempt in range(1, _CONNECT_ATTEMPTS + 1):
        try:
            await driver.verify_connectivity()

            return
        except ServiceUnavailable as exc:
            last_error = exc
            if attempt == _CONNECT_ATTEMPTS:
                break
            logger.warning(
                "neo4j not ready (attempt %s/%s), retrying in %.1fs",
                attempt,
                _CONNECT_ATTEMPTS,
                delay,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, _CONNECT_BACKOFF_CAP_SECONDS)

    raise last_error if last_error else ServiceUnavailable("neo4j unreachable")


async def get_driver() -> AsyncDriver:
    """Return the process-wide Neo4j driver, opening it on first use.

    One driver per process, not per call: the driver owns a connection pool and
    constructing one per query opens a fresh pool each time, which collapses
    under upsert load.

    Returns:
        The shared ``AsyncDriver``.
    """
    global _driver

    if _driver is not None:
        return _driver

    async with _driver_lock:
        if _driver is None:
            driver = _build_driver()
            try:
                await _verify_with_backoff(driver)
            except BaseException:
                await driver.close()
                raise
            _driver = driver

    return _driver


async def connect() -> AsyncDriver:
    """Open the driver and apply the schema. Call on API startup and worker init.

    Both steps are idempotent, so calling this twice in one process is safe.

    Returns:
        The shared ``AsyncDriver``.
    """
    driver = await get_driver()
    await apply_schema(driver)

    return driver


async def close() -> None:
    """Close the process-wide driver. Call on API shutdown and worker teardown."""
    global _driver

    async with _driver_lock:
        if _driver is not None:
            await _driver.close()
            _driver = None


@asynccontextmanager
async def session(**kwargs: Any) -> AsyncIterator[AsyncSession]:
    """Yield a Neo4j session bound to the configured database.

    Args:
        **kwargs: Extra arguments forwarded to ``AsyncDriver.session``.

    Yields:
        An ``AsyncSession`` for ``settings.neo4j_database``.
    """
    driver = await get_driver()
    async with driver.session(
        database=settings.neo4j_database, **kwargs
    ) as neo_session:
        yield neo_session


async def apply_schema(driver: AsyncDriver | None = None) -> None:
    """Create the constraints and indexes the projection depends on.

    Every statement is ``IF NOT EXISTS``, so this runs on every startup.

    Args:
        driver: Driver to use. Defaults to the process-wide one.
    """
    driver = driver or await get_driver()
    async with driver.session(database=settings.neo4j_database) as neo_session:
        for statement in SCHEMA_STATEMENTS:
            await neo_session.run(statement)  # type: ignore[arg-type]


async def healthcheck() -> tuple[bool, str]:
    """Report driver connectivity for the ``/health`` dependency probe.

    Returns:
        ``(ok, detail)`` — never raises, because a health endpoint that raises
        reports nothing.
    """
    try:
        driver = await get_driver()
        await driver.verify_connectivity()
    except (ServiceUnavailable, Neo4jError, OSError) as exc:
        return False, f"{type(exc).__name__}: {exc}"

    return True, settings.neo4j_uri


async def execute(query: str, /, **parameters: Any) -> Any:
    """Run one query as a managed transaction, retried on transient failures.

    Managed transactions are what make a Neo4j container restart survivable
    without restarting the API: the driver retries through the reconnect window
    instead of surfacing ``ServiceUnavailable`` to the caller. Use this for
    single statements; use ``session()`` when several statements must share one
    session.

    Args:
        query: Cypher to run.
        **parameters: Query parameters.

    Returns:
        The driver's ``EagerResult`` — records, summary and keys.
    """
    driver = await get_driver()
    result = await driver.execute_query(
        query, parameters_=parameters, database_=settings.neo4j_database
    )

    return result

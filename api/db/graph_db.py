from contextlib import asynccontextmanager

from neo4j import AsyncGraphDatabase

URI = "neo4j://localhost:7687"
AUTH = ("neo4j", "very_safe_password")


@asynccontextmanager
async def graph_db_session():
    async with AsyncGraphDatabase.driver(URI, auth=AUTH) as driver:
        yield driver


async def create_nodes() -> None:
    """Not implemented.

    Superseded by ``api/graph/client.py`` in S1.4, which owns the driver
    lifecycle, the schema constraints and ``graph.reset(book_id)``.
    """
    raise NotImplementedError(
        "Graph writes land in S1.4 — see plans/sprint-1/backend-2.md"
    )

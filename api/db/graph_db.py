from contextlib import asynccontextmanager

from neo4j import AsyncGraphDatabase

URI = "neo4j://localhost:7687"
AUTH = ("neo4j", "very_safe_password")


@asynccontextmanager
async def graph_db_session():
    async with AsyncGraphDatabase.driver(URI, auth=AUTH) as driver:
        yield driver


async def create_nodes():

    async with graph_db_session() as session:
        create_query = """
            CREATE
        """

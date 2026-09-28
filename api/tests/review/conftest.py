import pytest_asyncio

from api.graph.checkpoint import setup_checkpointer


@pytest_asyncio.fixture(scope="session", autouse=True)
async def checkpointer_schema():
    """Create the LangGraph checkpoint tables once. Idempotent (S1.6); shared
    with ``api/tests/graph/test_checkpointer.py`` but that fixture is scoped
    to its own module, not the whole run.
    """
    await setup_checkpointer()

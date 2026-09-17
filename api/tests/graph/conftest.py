import uuid

import pytest

from api.graph import client, projection


@pytest.fixture(scope="session", autouse=True)
async def neo4j_driver():
    """Open the process-wide driver once and apply the schema, as startup does."""
    await client.connect()
    yield
    await client.close()


@pytest.fixture
def project_id() -> str:
    """A fresh project namespace, so one test never sees another's subgraph."""
    return str(uuid.uuid4())


@pytest.fixture
async def clean_project(project_id: str):
    """Yield a project id and drop its subgraph afterwards."""
    yield project_id
    await projection.reset_project(project_id)

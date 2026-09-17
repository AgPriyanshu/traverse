import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from api.db.engine import db_session
from api.db.models.project_model import Book, Project
from api.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Drive the real app in-process, against the real traverse_be2 Postgres."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
async def project() -> AsyncIterator[Project]:
    """Create an empty project and delete it afterwards."""
    row = Project(
        name="Fixture project",
        slug=f"fixture-{uuid.uuid4()}",
    )
    async with db_session() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)

    yield row

    async with db_session() as session:
        stored = await session.get(Book, row.id)
        if stored is not None:
            await session.delete(stored)
            await session.commit()

    async with db_session() as session:
        stored = await session.get(Project, row.id)
        if stored is not None:
            await session.delete(stored)
            await session.commit()


@pytest.fixture
async def book(project: Project) -> AsyncIterator[Book]:
    """Create one book in the fixture project."""
    row = Book(
        project_id=project.id,
        series_order=1,
        title="Fixture book",
        content_hash=str(uuid.uuid4()),
    )
    async with db_session() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)

    yield row

    async with db_session() as session:
        stored = await session.get(Book, row.id)
        if stored is not None:
            await session.delete(stored)
            await session.commit()

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

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

    # A raw DELETE, not ``session.get`` + ``session.delete``: the latter
    # loads the ORM relationship graph (``Project.books``, ``Book.chapters``,
    # ...) and, without ``passive_deletes=True`` on those relationships
    # (``api/db/models/**`` is orchestrator-owned, not ours to add it to),
    # SQLAlchemy tries to null out each child's NOT NULL foreign key itself
    # instead of leaving it to the DB. A raw statement never touches the ORM
    # cascade machinery, so Postgres's own ``ON DELETE CASCADE`` (already
    # declared on every one of these FKs) does the actual cleanup — which is
    # also just correct: a test that seeded chapters, chunks, characters or
    # mentions off this project must not need to know that to clean up.
    async with db_session() as session:
        await session.execute(delete(Project).where(Project.id == row.id))
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

    # See ``project``'s teardown above for why this is a raw statement.
    async with db_session() as session:
        await session.execute(delete(Book).where(Book.id == row.id))
        await session.commit()

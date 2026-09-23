import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

# Tests must never reach the network: a model download at test time turns a
# 10-second suite into a 20-minute one and fails outright in CI.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("EMBEDDING_DEVICE", "cpu")

from api.contracts.enums import ProjectKind  # noqa: E402
from api.db.engine import engine  # noqa: E402
from api.db.models import Book, Project  # noqa: E402

TABLES_TOUCHED_BY_TESTS = (
    "ingestionstage",
    "ingestionrun",
    "documentchunk",
    "chapter",
    "charactermention",
    "characterappearance",
    "character",
    "bookcharactercandidate",
    "rejectedcandidate",
    "reviewtask",
    "book",
    "project",
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[SQLModelAsyncSession]:
    """An async session against the real database, truncated after each test.

    ``expire_on_commit=False`` because the repository commits inside its own
    calls: with the default, every ORM object a test is holding is expired the
    moment a repository function commits, and the next attribute read attempts
    lazy IO outside the greenlet. A request-scoped session never sees this.
    """
    async with SQLModelAsyncSession(engine, expire_on_commit=False) as db_session:
        yield db_session

    tables = ", ".join(TABLES_TOUCHED_BY_TESTS)

    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def project(session: SQLModelAsyncSession) -> Project:
    """A saved project to hang books off."""
    row = Project(
        name="Test Project",
        slug=f"test-{uuid.uuid4().hex[:8]}",
        kind=ProjectKind.STANDALONE,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return row


@pytest_asyncio.fixture
async def book(session: SQLModelAsyncSession, project: Project) -> Book:
    """A saved book in ``project``."""
    row = Book(
        project_id=project.id,
        title="The Test Novel",
        author="A. Tester",
        content_hash=uuid.uuid4().hex,
        page_count=3,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return row


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"

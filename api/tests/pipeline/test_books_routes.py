import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import BookStatus, StageName, StageState
from api.db.engine import get_session
from api.db.models import Book, Project
from api.main import app
from api.pipeline import repository
from api.workers.errors import PermanentError
from api.workers.stages import stage


@pytest_asyncio.fixture
async def client(session: SQLModelAsyncSession) -> AsyncIterator[AsyncClient]:
    """An ASGI client sharing the test's session, so it sees uncommitted setup."""

    async def override() -> AsyncIterator[SQLModelAsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http

    app.dependency_overrides.clear()


class TestListProjects:
    async def test_an_empty_install_returns_an_empty_list(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/projects")

        assert response.status_code == 200
        assert response.json() == []

    async def test_a_project_reports_its_counts(
        self, client: AsyncClient, project: Project, book: Book
    ) -> None:
        response = await client.get("/api/projects")
        body = response.json()

        assert response.status_code == 200
        assert len(body) == 1
        assert body[0]["slug"] == project.slug
        assert body[0]["book_count"] == 1
        assert body[0]["character_count"] == 0


class TestGetProject:
    async def test_returns_the_project_and_its_books(
        self, client: AsyncClient, project: Project, book: Book
    ) -> None:
        response = await client.get(f"/api/projects/{project.id}")
        body = response.json()

        assert response.status_code == 200
        assert [entry["id"] for entry in body["books"]] == [str(book.id)]

    async def test_an_unknown_project_is_404_not_501(self, client: AsyncClient) -> None:
        response = await client.get(f"/api/projects/{uuid.uuid4()}")

        assert response.status_code == 404


class TestGetBook:
    async def test_returns_the_book(self, client: AsyncClient, book: Book) -> None:
        response = await client.get(f"/api/books/{book.id}")
        body = response.json()

        assert response.status_code == 200
        assert body["title"] == "The Test Novel"
        assert body["status"] == BookStatus.QUEUED.value
        assert body["ingested_at"] is None

    async def test_an_unknown_book_is_404(self, client: AsyncClient) -> None:
        response = await client.get(f"/api/books/{uuid.uuid4()}")

        assert response.status_code == 404


class TestGetBookStatus:
    async def test_a_book_that_has_not_started_has_no_stages(
        self, client: AsyncClient, book: Book
    ) -> None:
        response = await client.get(f"/api/books/{book.id}/status")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == BookStatus.QUEUED.value
        assert body["stages"] == []

    async def test_stages_are_reported_in_pipeline_order(
        self, client: AsyncClient, session: SQLModelAsyncSession, book: Book
    ) -> None:
        async with stage(book.id, StageName.PARSE_AND_CHUNK) as record:
            record.rows_written = 3
        async with stage(book.id, StageName.SEGMENT_CHAPTERS):
            pass

        await repository.set_book_status(session, book.id, BookStatus.PROCESSING)

        response = await client.get(f"/api/books/{book.id}/status")
        body = response.json()

        assert [entry["stage"] for entry in body["stages"]] == [
            StageName.PARSE_AND_CHUNK.value,
            StageName.SEGMENT_CHAPTERS.value,
        ]
        assert all(
            entry["state"] == StageState.SUCCEEDED.value for entry in body["stages"]
        )
        assert body["stages"][0]["duration_ms"] is not None

    async def test_a_failed_stage_carries_its_error_to_the_client(
        self, client: AsyncClient, book: Book
    ) -> None:
        try:
            async with stage(book.id, StageName.PARSE_AND_CHUNK):
                raise PermanentError("cannot convert novel.pdf")
        except PermanentError:
            pass

        response = await client.get(f"/api/books/{book.id}/status")
        failed = response.json()["stages"][0]

        assert failed["state"] == StageState.FAILED.value
        assert failed["error"] == "cannot convert novel.pdf"
        assert failed["attempt"] == 1

    async def test_an_unknown_book_is_404(self, client: AsyncClient) -> None:
        response = await client.get(f"/api/books/{uuid.uuid4()}/status")

        assert response.status_code == 404


class TestStillFrozen:
    """Endpoints that must keep returning 501 until their sprint lands.

    Shipping half of upload now means FE1 codes against a shape that changes.
    """

    async def test_upload_is_still_a_stub(
        self, client: AsyncClient, project: Project
    ) -> None:
        response = await client.post(
            f"/api/projects/{project.id}/books",
            files={"file": ("novel.pdf", b"%PDF-1.4", "application/pdf")},
        )

        assert response.status_code == 501

    async def test_the_openapi_document_still_lists_every_frozen_path(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/openapi.json")

        assert len(response.json()["paths"]) == 33

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import BookStatus, StageName, StageState
from api.contracts.pipeline import ChapterInfo, ChunkPayload
from api.db.engine import get_session
from api.db.models import Book, Project
from api.main import app
from api.pipeline import repository
from api.pipeline.storage import store
from api.workers.errors import PermanentError
from api.workers.stages import stage

from ._pdf_helpers import minimal_pdf_with_metadata

FIXTURE = Path(__file__).parent.parent / "fixtures" / "three_page_novel.pdf"


def _payload(page: int, chapter: int | None = None) -> ChunkPayload:
    return ChunkPayload(
        text=f"Passage on page {page}.",
        pages=[page, page + 1],
        page_start=page,
        page_end=page + 1,
        chapter_number=chapter,
        token_count=7,
    )


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
    # Real MinIO, not a mock: clean up anything an upload test wrote so the
    # bucket does not accumulate across runs.
    await store.delete_prefix("books/")


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


class TestUploadBook:
    async def test_a_new_pdf_is_stored_and_queued(
        self, client: AsyncClient, project: Project
    ) -> None:
        response = await client.post(
            f"/api/projects/{project.id}/books",
            files={
                "file": (
                    "three_page_novel.pdf",
                    FIXTURE.read_bytes(),
                    "application/pdf",
                )
            },
        )
        body = response.json()

        assert response.status_code == 202
        assert body["status"] == BookStatus.QUEUED.value
        assert body["title"] == "Three Page Novel"

    async def test_title_and_author_come_from_pdf_metadata_when_present(
        self, client: AsyncClient, project: Project
    ) -> None:
        response = await client.post(
            f"/api/projects/{project.id}/books",
            files={
                "file": (
                    "whatever.pdf",
                    minimal_pdf_with_metadata("Pride and Prejudice", "Jane Austen"),
                    "application/pdf",
                )
            },
        )
        body = response.json()

        assert body["title"] == "Pride and Prejudice"
        assert body["author"] == "Jane Austen"

    async def test_an_identical_upload_is_not_re_stored(
        self, client: AsyncClient, project: Project, session: SQLModelAsyncSession
    ) -> None:
        content = FIXTURE.read_bytes()
        files = {"file": ("three_page_novel.pdf", content, "application/pdf")}

        first = await client.post(f"/api/projects/{project.id}/books", files=files)
        second = await client.post(f"/api/projects/{project.id}/books", files=files)

        assert first.status_code == 202
        assert second.status_code == 200
        assert second.json() == {
            "status": "already_ingested",
            "book_id": first.json()["id"],
        }
        assert await repository.count_books(session) == 1

    async def test_a_non_pdf_is_rejected_with_the_content_type_named(
        self, client: AsyncClient, project: Project
    ) -> None:
        response = await client.post(
            f"/api/projects/{project.id}/books",
            files={"file": ("notes.txt", b"just some text", "text/plain")},
        )

        assert response.status_code == 415
        assert "notes.txt" in response.json()["detail"]

    async def test_an_empty_upload_is_rejected(
        self, client: AsyncClient, project: Project
    ) -> None:
        response = await client.post(
            f"/api/projects/{project.id}/books",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )

        assert response.status_code == 400

    async def test_an_unknown_project_is_404(self, client: AsyncClient) -> None:
        response = await client.post(
            f"/api/projects/{uuid.uuid4()}/books",
            files={"file": ("novel.pdf", FIXTURE.read_bytes(), "application/pdf")},
        )

        assert response.status_code == 404


class TestReprocessBook:
    async def test_resumes_from_the_first_incomplete_stage_by_default(
        self, client: AsyncClient, book: Book
    ) -> None:
        async with stage(book.id, StageName.PARSE_AND_CHUNK):
            pass
        try:
            async with stage(book.id, StageName.SEGMENT_CHAPTERS):
                raise PermanentError("boom")
        except PermanentError:
            pass

        response = await client.post(f"/api/books/{book.id}/reprocess")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == BookStatus.PROCESSING.value

    async def test_an_explicit_stage_is_honoured(
        self, client: AsyncClient, book: Book
    ) -> None:
        response = await client.post(
            f"/api/books/{book.id}/reprocess",
            params={"from_stage": StageName.EMBED_CHUNKS.value},
        )

        assert response.status_code == 200

    async def test_an_unknown_stage_name_is_a_400(
        self, client: AsyncClient, book: Book
    ) -> None:
        response = await client.post(
            f"/api/books/{book.id}/reprocess",
            params={"from_stage": "not.a.real.stage"},
        )

        assert response.status_code == 400

    async def test_nothing_to_reprocess_once_everything_succeeded(
        self, client: AsyncClient, book: Book
    ) -> None:
        for stage_name in StageName:
            async with stage(book.id, stage_name):
                pass

        response = await client.post(f"/api/books/{book.id}/reprocess")

        assert response.status_code == 400

    async def test_an_unknown_book_is_404(self, client: AsyncClient) -> None:
        response = await client.post(f"/api/books/{uuid.uuid4()}/reprocess")

        assert response.status_code == 404


class TestListChapters:
    async def test_returns_chapters_with_chunk_counts(
        self, client: AsyncClient, session: SQLModelAsyncSession, book: Book
    ) -> None:
        await repository.upsert_chapters(
            session,
            book.id,
            [
                ChapterInfo(is_chapter=True, number=1, title="One"),
                ChapterInfo(is_chapter=True, number=2, title="Two"),
            ],
            page_ranges={1: (1, 9), 2: (10, 20)},
        )
        await repository.bulk_insert_chunks(
            session,
            book.id,
            [
                _payload(page=3, chapter=1),
                _payload(page=5, chapter=1),
                _payload(page=12, chapter=2),
            ],
        )
        await repository.assign_chunk_chapters(session, book.id)

        response = await client.get(f"/api/books/{book.id}/chapters")
        body = response.json()

        assert response.status_code == 200
        assert [entry["number"] for entry in body] == [1, 2]
        assert [entry["chunk_count"] for entry in body] == [2, 1]

    async def test_an_unknown_book_is_404(self, client: AsyncClient) -> None:
        response = await client.get(f"/api/books/{uuid.uuid4()}/chapters")

        assert response.status_code == 404


class TestListChunks:
    async def test_returns_chunks_in_page_order(
        self, client: AsyncClient, session: SQLModelAsyncSession, book: Book
    ) -> None:
        await repository.bulk_insert_chunks(
            session, book.id, [_payload(page=5), _payload(page=2)]
        )

        response = await client.get(f"/api/books/{book.id}/chunks")
        body = response.json()

        assert response.status_code == 200
        assert [entry["page_start"] for entry in body] == [2, 5]

    async def test_limit_is_respected(
        self, client: AsyncClient, session: SQLModelAsyncSession, book: Book
    ) -> None:
        await repository.bulk_insert_chunks(
            session, book.id, [_payload(page=1), _payload(page=3)]
        )

        response = await client.get(f"/api/books/{book.id}/chunks?limit=1")

        assert len(response.json()) == 1

    async def test_an_unknown_book_is_404(self, client: AsyncClient) -> None:
        response = await client.get(f"/api/books/{uuid.uuid4()}/chunks")

        assert response.status_code == 404


class TestStillFrozen:
    """Endpoints that must keep returning 501 until their sprint lands."""

    async def test_the_openapi_document_still_lists_every_frozen_path(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/openapi.json")

        # 33 frozen at the Sprint 1 freeze, +1 for GET /books at Sprint 2's
        # (SCR-6: a flat list so the library screen isn't an N+1), +2 at
        # Sprint 3's for GET /ops/extraction-quality and
        # GET /ops/extraction-cost (do1's SCR-3: this exact assertion
        # collides with any sprint that adds a route in any agent's owned
        # router — bumped here at the merge train once the final count
        # across all four branches was known, same as Sprint 2's SCR-6).
        assert len(response.json()["paths"]) == 36

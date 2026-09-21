"""Failure injection for the ingestion chain (S2.5).

Each test breaks one real, documented failure mode — a corrupt PDF, a dropped
connection, a worker killed mid-batch, a missing upstream artifact — and
checks the property that actually matters: work already committed survives,
the error is classified correctly for Celery's retry policy, and the book
stays recoverable rather than silently corrupted or duplicated.
"""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import BookStatus, StageName, StageState
from api.contracts.pipeline import ChapterInfo, ChunkPayload, StageStatus
from api.db.engine import get_session
from api.db.models import Book, Project
from api.main import app
from api.pipeline import repository, tasks
from api.pipeline.errors import DocumentParseError
from api.pipeline.storage import StorageError, store
from api.routes.books import _first_incomplete_stage
from api.workers.errors import PermanentError, TransientError
from api.workers.stages import StageRecord, stage

from ._pdf_helpers import minimal_pdf_with_metadata


@pytest_asyncio.fixture(autouse=True)
async def _clean_bucket() -> AsyncIterator[None]:
    """Real MinIO, not a mock: nothing must survive between tests."""
    yield
    await store.delete_prefix("books/")


@pytest_asyncio.fixture
async def client(session: SQLModelAsyncSession) -> AsyncIterator[AsyncClient]:
    async def override() -> AsyncIterator[SQLModelAsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http

    app.dependency_overrides.clear()


def _record(stage_name: StageName) -> StageRecord:
    return StageRecord(run_id=uuid4(), stage_id=uuid4(), stage=stage_name, attempt=1)


async def _uploaded_book(
    session: SQLModelAsyncSession, project: Project, *, content: bytes | None = None
) -> Book:
    """A book row whose ``storage_key`` points at a real object in MinIO."""
    book_id = uuid.uuid4()
    storage_key = f"books/{book_id}/source.pdf"
    row = Book(
        id=book_id,
        project_id=project.id,
        title="Test Novel",
        content_hash=uuid.uuid4().hex,
        storage_key=storage_key,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    tmp = Path(f"/tmp/{book_id}-source.pdf")
    tmp.write_bytes(content or minimal_pdf_with_metadata("Test Novel", "A. Author"))
    try:
        await store.put_stream(storage_key, tmp, content_type="application/pdf")
    finally:
        tmp.unlink(missing_ok=True)

    return row


class _FakeChunker:
    """A real Docling conversion is not the point of these tests — see
    ``test_chunking.py`` for that. This stands in so a real Postgres row and a
    real MinIO object are exercised without paying for a real conversion.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def load_document(self, path: Path) -> object:
        class _Doc:
            pages = {1: object(), 2: object()}

        return _Doc()

    async def prepare_chapters(self, document: object, *, book_id: str | None = None):
        return []

    async def detect_chapters(
        self, document: object, *, book_id: str | None = None, prepared=None
    ) -> list[ChapterInfo]:
        return [ChapterInfo(is_chapter=True, number=1, text="Chapter 1")]

    async def generate_chunks(
        self,
        document: object,
        *,
        embed: bool = True,
        book_id: str | None = None,
        prepared=None,
    ) -> list[ChunkPayload]:
        return [
            ChunkPayload(
                text="Passage one.",
                pages=[1],
                page_start=1,
                page_end=1,
                chapter_number=1,
                token_count=4,
            ),
            ChunkPayload(
                text="Passage two.",
                pages=[2],
                page_start=2,
                page_end=2,
                chapter_number=1,
                token_count=4,
            ),
        ]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1024 for _ in texts]


@pytest.fixture(autouse=True)
def _stub_chunker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks, "DocumentChunker", _FakeChunker)


class TestUpstreamWorkSurvivesADownstreamFailure:
    async def test_chunks_survive_a_segment_chapters_failure(
        self, session: SQLModelAsyncSession, project: Project
    ) -> None:
        book = await _uploaded_book(session, project)
        await tasks._parse_and_chunk(book.id, _record(StageName.PARSE_AND_CHUNK))
        before = await repository.count_chunks(session, book.id)

        # The chapters artifact parse_and_chunk hands off is gone — segment
        # cannot run, but nothing it would have written should touch what
        # parse already committed.
        await store.delete_prefix(f"books/{book.id}/chapters.json")

        with pytest.raises(PermanentError):
            await tasks._segment_chapters(book.id, _record(StageName.SEGMENT_CHAPTERS))

        after = await repository.count_chunks(session, book.id)
        assert after == before == 2

    async def test_an_embed_failure_does_not_touch_already_written_chunks(
        self,
        session: SQLModelAsyncSession,
        project: Project,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        book = await _uploaded_book(session, project)
        await tasks._parse_and_chunk(book.id, _record(StageName.PARSE_AND_CHUNK))
        await tasks._segment_chapters(book.id, _record(StageName.SEGMENT_CHAPTERS))

        # Each chunk alone fills the batch budget, forcing a flush between
        # them — the crash below lands on the second flush.
        monkeypatch.setattr(tasks, "_EMBED_BATCH_TOKEN_BUDGET", 1)

        def crash_on_second_batch(
            self: _FakeChunker, texts: list[str]
        ) -> list[list[float]]:
            crash_on_second_batch.calls += 1
            if crash_on_second_batch.calls == 1:
                return [[0.01] * 1024 for _ in texts]
            raise RuntimeError("embedding backend crashed")

        crash_on_second_batch.calls = 0
        monkeypatch.setattr(_FakeChunker, "embed_texts", crash_on_second_batch)

        with pytest.raises(RuntimeError):
            await tasks._embed_chunks(book.id, _record(StageName.EMBED_CHUNKS))

        pending = await repository.list_chunks_needing_embedding(session, book.id)
        assert len(pending) == 1  # the chunk whose batch never got its turn

        # A restart with a working embedder touches only what is still
        # missing, and re-embeds nothing that already succeeded (F1.2).
        def always_succeeds(self: _FakeChunker, texts: list[str]) -> list[list[float]]:
            return [[0.02] * 1024 for _ in texts]

        monkeypatch.setattr(_FakeChunker, "embed_texts", always_succeeds)
        await tasks._embed_chunks(book.id, _record(StageName.EMBED_CHUNKS))

        assert await repository.list_chunks_needing_embedding(session, book.id) == []


class TestPermanentFailuresWriteNothingPartial:
    async def test_a_malformed_pdf_is_permanent_not_transient(
        self,
        session: SQLModelAsyncSession,
        project: Project,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.undo()  # use the real chunker so Docling actually runs
        book = await _uploaded_book(session, project, content=b"not a pdf at all")

        with pytest.raises(DocumentParseError) as excinfo:
            await tasks._parse_and_chunk(book.id, _record(StageName.PARSE_AND_CHUNK))

        assert not isinstance(excinfo.value, TransientError)
        assert await repository.count_chunks(session, book.id) == 0

    async def test_a_missing_source_object_writes_no_partial_chunks(
        self, session: SQLModelAsyncSession, project: Project
    ) -> None:
        book_id = uuid.uuid4()
        row = Book(
            id=book_id,
            project_id=project.id,
            title="Ghost Novel",
            content_hash=uuid.uuid4().hex,
            storage_key=f"books/{book_id}/source.pdf",
        )
        session.add(row)
        await session.commit()

        with pytest.raises(PermanentError):
            await tasks._parse_and_chunk(book_id, _record(StageName.PARSE_AND_CHUNK))

        assert await repository.count_chunks(session, book_id) == 0


class TestTransientFailuresAreClassifiedForRetry:
    async def test_a_dropped_connection_fetching_the_source_is_transient(
        self,
        session: SQLModelAsyncSession,
        project: Project,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        book = await _uploaded_book(session, project)

        async def flaky_get_object(key: str, dest: Path) -> None:
            raise StorageError("connection reset by peer")

        monkeypatch.setattr(store, "get_object", flaky_get_object)

        with pytest.raises(TransientError):
            await tasks._parse_and_chunk(book.id, _record(StageName.PARSE_AND_CHUNK))


class TestHumanVerifiedChaptersSurviveReprocessing:
    async def test_a_verified_chapter_is_not_clobbered_by_re_segmentation(
        self, session: SQLModelAsyncSession, project: Project
    ) -> None:
        book = await _uploaded_book(session, project)
        await tasks._parse_and_chunk(book.id, _record(StageName.PARSE_AND_CHUNK))
        await tasks._segment_chapters(book.id, _record(StageName.SEGMENT_CHAPTERS))

        chapters = await repository.list_chapters(session, book.id)
        chapters[0].title = "Human-Corrected Title"
        chapters[0].human_verified = True
        session.add(chapters[0])
        await session.commit()

        # Re-running segmentation from the same artifact must not overwrite
        # the correction (F5.4), even though the detector still reports its
        # own title for the same chapter number.
        await tasks._segment_chapters(book.id, _record(StageName.SEGMENT_CHAPTERS))

        chapters_after = await repository.list_chapters(session, book.id)
        assert chapters_after[0].title == "Human-Corrected Title"
        assert chapters_after[0].human_verified is True


class TestABookStaysRecoverableAfterADeadLetter:
    def test_reprocess_resumes_from_the_failing_stage_not_the_start(self) -> None:
        statuses = [
            StageStatus(stage=StageName.PARSE_AND_CHUNK, state=StageState.SUCCEEDED),
            StageStatus(stage=StageName.SEGMENT_CHAPTERS, state=StageState.FAILED),
        ]

        assert _first_incomplete_stage(statuses) is StageName.SEGMENT_CHAPTERS
        assert _first_incomplete_stage([]) is StageName.PARSE_AND_CHUNK

        every_stage_done = [
            StageStatus(stage=name, state=StageState.SUCCEEDED) for name in StageName
        ]
        assert _first_incomplete_stage(every_stage_done) is None

    async def test_the_status_endpoint_reports_the_dead_letter(
        self, client: AsyncClient, session: SQLModelAsyncSession, project: Project
    ) -> None:
        book = await _uploaded_book(session, project)
        await tasks._parse_and_chunk(book.id, _record(StageName.PARSE_AND_CHUNK))

        try:
            async with stage(book.id, StageName.SEGMENT_CHAPTERS):
                raise PermanentError("no chapters artifact for this book")
        except PermanentError:
            pass

        response = await client.get(f"/api/books/{book.id}/status")
        body = response.json()

        failed = next(
            entry
            for entry in body["stages"]
            if entry["stage"] == StageName.SEGMENT_CHAPTERS.value
        )
        assert response.status_code == 200
        assert body["status"] == BookStatus.FAILED.value
        assert failed["state"] == StageState.FAILED.value
        assert failed["error"] == "no chapters artifact for this book"

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import DetectionMethod, StageName
from api.contracts.pipeline import ChapterInfo, ChunkPayload
from api.db.models import Book, Project
from api.pipeline import repository, tasks
from api.pipeline.storage import store
from api.workers.errors import PermanentError
from api.workers.stages import StageRecord

from ._pdf_helpers import minimal_pdf_with_metadata


@pytest_asyncio.fixture(autouse=True)
async def _clean_bucket() -> AsyncIterator[None]:
    """Real MinIO, not a mock: nothing must survive between tests."""
    yield
    await store.delete_prefix("books/")


def _record(stage: StageName) -> StageRecord:
    return StageRecord(run_id=uuid4(), stage_id=uuid4(), stage=stage, attempt=1)


class _FakeChunker:
    """Stands in for ``DocumentChunker`` so these tests exercise the task's own
    orchestration — fetch, persist, idempotent replace, the chapters artifact
    handoff — without paying for a real Docling conversion. The chunker's own
    correctness is covered in ``test_chunking.py``/``test_chunking_document.py``.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def load_document(self, path: Path) -> object:
        assert path.exists()

        class _Doc:
            pages = {1: object(), 2: object(), 3: object()}

        return _Doc()

    async def prepare_chapters(self, document: object, *, book_id: str | None = None):
        return []

    async def detect_chapters(
        self, document: object, *, book_id: str | None = None, prepared=None
    ) -> list[ChapterInfo]:
        return [
            ChapterInfo(
                is_chapter=True,
                number=1,
                title=None,
                text="Chapter 1",
                detection_method=DetectionMethod.REGEX,
            ),
            ChapterInfo(
                is_chapter=True,
                number=2,
                title=None,
                text="Chapter 2",
                detection_method=DetectionMethod.REGEX,
            ),
        ]

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
            ChunkPayload(
                text="Passage three.",
                pages=[3],
                page_start=3,
                page_end=3,
                chapter_number=2,
                token_count=4,
            ),
        ]


@pytest.fixture(autouse=True)
def _stub_chunker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks, "DocumentChunker", _FakeChunker)


@pytest_asyncio.fixture
async def uploaded_book(session: SQLModelAsyncSession, project: Project) -> Book:
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
    tmp.write_bytes(minimal_pdf_with_metadata("Test Novel", "A. Author"))
    try:
        await store.put_stream(storage_key, tmp, content_type="application/pdf")
    finally:
        tmp.unlink(missing_ok=True)

    return row


class TestParseAndChunk:
    async def test_writes_chunks_page_count_and_chapters_artifact(
        self, session: SQLModelAsyncSession, uploaded_book: Book
    ) -> None:
        record = _record(StageName.PARSE_AND_CHUNK)

        await tasks._parse_and_chunk(uploaded_book.id, record)

        chunks = await repository.list_chunks(session, uploaded_book.id, limit=10)
        assert len(chunks) == 3
        assert record.rows_written == 3

        # ``_parse_and_chunk`` commits through its own session; this session
        # already has ``uploaded_book`` in its identity map from the fixture
        # and (``expire_on_commit=False``) will not see the other session's
        # write without an explicit refresh.
        refreshed = await repository.get_book(session, uploaded_book.id)
        assert refreshed is not None
        await session.refresh(refreshed)
        assert refreshed.page_count == 3

        assert await store.exists(f"books/{uploaded_book.id}/chapters.json")

    async def test_a_rerun_replaces_rather_than_appends(
        self, session: SQLModelAsyncSession, uploaded_book: Book
    ) -> None:
        stage_name = StageName.PARSE_AND_CHUNK
        await tasks._parse_and_chunk(uploaded_book.id, _record(stage_name))
        await tasks._parse_and_chunk(uploaded_book.id, _record(stage_name))

        total = await repository.count_chunks(session, uploaded_book.id)
        assert total == 3

    async def test_a_missing_source_object_is_permanent(
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

    async def test_a_book_with_no_storage_key_is_permanent(
        self, session: SQLModelAsyncSession, project: Project
    ) -> None:
        row = Book(
            project_id=project.id,
            title="Never Uploaded",
            content_hash=uuid.uuid4().hex,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)

        with pytest.raises(PermanentError):
            await tasks._parse_and_chunk(row.id, _record(StageName.PARSE_AND_CHUNK))


class TestSegmentChapters:
    async def test_persists_chapters_and_backfills_chunk_ids(
        self, session: SQLModelAsyncSession, uploaded_book: Book
    ) -> None:
        parse_record = _record(StageName.PARSE_AND_CHUNK)
        await tasks._parse_and_chunk(uploaded_book.id, parse_record)

        record = _record(StageName.SEGMENT_CHAPTERS)
        await tasks._segment_chapters(uploaded_book.id, record)

        chapters = await repository.list_chapters(session, uploaded_book.id)
        assert [c.number for c in chapters] == [1, 2]
        assert chapters[0].page_start == 1
        assert chapters[0].page_end == 2
        assert chapters[1].page_start == 3
        assert chapters[1].page_end == 3

        chunks = await repository.list_chunks(session, uploaded_book.id, limit=10)
        assert all(chunk.chapter_id is not None for chunk in chunks)
        assert record.rows_written == 3

    async def test_a_missing_artifact_is_permanent(
        self, session: SQLModelAsyncSession, uploaded_book: Book
    ) -> None:
        with pytest.raises(PermanentError):
            await tasks._segment_chapters(
                uploaded_book.id, _record(StageName.SEGMENT_CHAPTERS)
            )

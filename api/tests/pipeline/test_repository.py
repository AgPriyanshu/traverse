import time
import uuid

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import BookStatus, DetectionMethod, StageName, StageState
from api.contracts.pipeline import ChapterInfo, ChunkPayload, StageStatus
from api.db.models import Book, DocumentChunk, Project
from api.pipeline import repository


def payload(page: int, chapter: int | None = 1, *, embed: bool = False) -> ChunkPayload:
    return ChunkPayload(
        text=f"Passage on page {page}.",
        text_embedding=[0.01] * 1024 if embed else None,
        pages=[page, page + 1],
        page_start=page,
        page_end=page + 1,
        chapter_number=chapter,
        token_count=7,
    )


class TestCreateBook:
    async def test_creates_a_book(
        self, session: SQLModelAsyncSession, project: Project
    ) -> None:
        book = await repository.create_book(
            session,
            project_id=project.id,
            title="Pride and Prejudice",
            author="Jane Austen",
            content_hash="hash-a",
            page_count=300,
        )

        assert book.id is not None
        assert book.status is BookStatus.QUEUED

    async def test_the_same_content_hash_returns_the_existing_row(
        self, session: SQLModelAsyncSession, project: Project
    ) -> None:
        first = await repository.create_book(
            session, project_id=project.id, title="A", content_hash="hash-b"
        )
        second = await repository.create_book(
            session,
            project_id=project.id,
            title="A second upload",
            content_hash="hash-b",
        )

        assert second.id == first.id
        assert second.title == "A"
        assert await repository.count_books(session) == 1

    async def test_lookup_by_hash(
        self, session: SQLModelAsyncSession, project: Project
    ) -> None:
        await repository.create_book(
            session, project_id=project.id, title="A", content_hash="hash-c"
        )

        assert await repository.get_book_by_hash(session, "hash-c") is not None
        assert await repository.get_book_by_hash(session, "absent") is None


class TestBulkInsertChunks:
    async def test_round_trips_page_provenance(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        written = await repository.bulk_insert_chunks(
            session, book.id, [payload(3), payload(5)]
        )

        assert written == 2

        stored = await repository.list_chunks(session, book.id)

        assert [chunk.pages for chunk in stored] == [[3, 4], [5, 6]]
        assert [chunk.page_start for chunk in stored] == [3, 5]
        assert [chunk.page_end for chunk in stored] == [4, 6]
        assert [chunk.token_count for chunk in stored] == [7, 7]

    async def test_an_empty_batch_writes_nothing(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        assert await repository.bulk_insert_chunks(session, book.id, []) == 0

    async def test_five_hundred_chunks_insert_in_under_two_seconds(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        payloads = [payload(page % 300 + 1, chapter=None) for page in range(500)]

        started = time.monotonic()
        written = await repository.bulk_insert_chunks(session, book.id, payloads)
        elapsed = time.monotonic() - started

        assert written == 500
        assert await repository.count_chunks(session, book.id) == 500
        # Row-by-row this is a 30-second stall; the point of the batch is that
        # it is not.
        assert elapsed < 2.0

    async def test_chunks_resolve_to_a_chapter_id_not_a_dangling_number(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        await repository.upsert_chapters(
            session,
            book.id,
            [ChapterInfo(is_chapter=True, number=1, title="One")],
            page_ranges={1: (1, 10)},
        )
        await repository.bulk_insert_chunks(session, book.id, [payload(3, chapter=1)])

        stored = await repository.list_chunks(session, book.id)
        chapters = await repository.list_chapters(session, book.id)

        assert stored[0].chapter_id == chapters[0].id

    async def test_an_unknown_chapter_number_leaves_chapter_id_null(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        await repository.bulk_insert_chunks(session, book.id, [payload(3, chapter=99)])
        stored = await repository.list_chunks(session, book.id)

        assert stored[0].chapter_id is None


class TestUpsertChapters:
    async def test_persists_chapters_with_page_ranges(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        chapters = await repository.upsert_chapters(
            session,
            book.id,
            [
                ChapterInfo(is_chapter=True, number=1, title="One", text="Chapter 1"),
                ChapterInfo(is_chapter=True, number=2, title="Two", text="Chapter 2"),
            ],
            page_ranges={1: (1, 9), 2: (10, 20)},
        )

        assert [chapter.number for chapter in chapters] == [1, 2]
        assert (chapters[0].page_start, chapters[0].page_end) == (1, 9)
        assert chapters[1].detection_method is DetectionMethod.REGEX

        refreshed = await session.get(Book, book.id)
        await session.refresh(refreshed)

        assert refreshed.chapter_count == 2

    async def test_re_segmentation_replaces_rather_than_duplicates(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        one = [ChapterInfo(is_chapter=True, number=1, title="One")]
        await repository.upsert_chapters(session, book.id, one, page_ranges={1: (1, 9)})
        again = await repository.upsert_chapters(
            session, book.id, one, page_ranges={1: (1, 12)}
        )

        assert len(again) == 1
        assert again[0].page_end == 12

    async def test_a_chapter_with_no_page_range_is_refused(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        with pytest.raises(ValueError, match="no page range"):
            await repository.upsert_chapters(
                session,
                book.id,
                [ChapterInfo(is_chapter=True, number=4)],
                page_ranges={1: (1, 9)},
            )

    async def test_an_empty_list_is_a_no_op(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        assert await repository.upsert_chapters(session, book.id, []) == []

    def test_page_ranges_are_derived_from_the_payloads(self) -> None:
        ranges = repository.page_ranges_from_payloads(
            [payload(1, 1), payload(5, 1), payload(11, 2)]
        )

        assert ranges == {1: (1, 6), 2: (11, 12)}


class TestAssignChunkChapters:
    async def test_backfills_chapter_id_from_page_ranges(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        await repository.bulk_insert_chunks(
            session, book.id, [payload(2, chapter=None), payload(12, chapter=None)]
        )
        await repository.upsert_chapters(
            session,
            book.id,
            [
                ChapterInfo(is_chapter=True, number=1),
                ChapterInfo(is_chapter=True, number=2),
            ],
            page_ranges={1: (1, 10), 2: (11, 20)},
        )

        assert await repository.assign_chunk_chapters(session, book.id) == 2

        rows = await repository.list_chapters(session, book.id)
        chapters = {chapter.number: chapter.id for chapter in rows}
        stored = await repository.list_chunks(session, book.id)

        assert [chunk.chapter_id for chunk in stored] == [chapters[1], chapters[2]]


class TestBookStatus:
    async def test_set_book_status(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        await repository.set_book_status(session, book.id, BookStatus.PROCESSING)
        refreshed = await session.get(Book, book.id)
        await session.refresh(refreshed)

        assert refreshed.status is BookStatus.PROCESSING

    async def test_a_book_with_no_run_has_no_stages(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        assert await repository.get_stage_statuses(session, book.id) == []

    def test_derive_status_from_stages(self) -> None:
        running = [
            StageStatus(stage=StageName.PARSE_AND_CHUNK, state=StageState.SUCCEEDED),
            StageStatus(stage=StageName.SEGMENT_CHAPTERS, state=StageState.RUNNING),
        ]
        failed = [
            StageStatus(stage=StageName.PARSE_AND_CHUNK, state=StageState.FAILED),
            StageStatus(stage=StageName.SEGMENT_CHAPTERS, state=StageState.RUNNING),
        ]
        finished = [
            StageStatus(stage=name, state=StageState.SUCCEEDED) for name in StageName
        ]

        assert repository.derive_book_status([]) is BookStatus.QUEUED
        assert repository.derive_book_status(running) is BookStatus.PROCESSING
        # A failure outranks a stage still running: the chain is already dead.
        assert repository.derive_book_status(failed) is BookStatus.FAILED
        assert repository.derive_book_status(finished) is BookStatus.READY


class TestReadModels:
    async def test_project_listing_counts_its_books(
        self, session: SQLModelAsyncSession, project: Project, book: Book
    ) -> None:
        projects = await repository.list_projects(session)
        mine = next(p for p in projects if p.id == project.id)

        assert mine.book_count == 1
        assert mine.character_count == 0
        assert mine.relation_count == 0

    async def test_project_detail_carries_its_books(
        self, session: SQLModelAsyncSession, project: Project, book: Book
    ) -> None:
        detail = await repository.get_project_detail(session, project.id)

        assert detail is not None
        assert [b.id for b in detail.books] == [book.id]

    async def test_a_missing_project_is_none(
        self, session: SQLModelAsyncSession
    ) -> None:
        assert await repository.get_project_detail(session, uuid.uuid4()) is None

    async def test_book_out_reports_no_ingested_at_until_ready(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        before = await repository.get_book_out(session, book.id)

        assert before is not None
        assert before.ingested_at is None

        await repository.set_book_status(session, book.id, BookStatus.READY)
        after = await repository.get_book_out(session, book.id)

        assert after is not None
        assert after.ingested_at is not None


class TestEmbeddingsRoundTrip:
    async def test_a_vector_survives_the_round_trip(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        await repository.bulk_insert_chunks(session, book.id, [payload(1, embed=True)])
        stored = await repository.list_chunks(session, book.id)

        assert stored[0].text_embedding is not None
        assert len(stored[0].text_embedding) == 1024


class TestPageProvenanceIsEnforcedByTheDatabase:
    async def test_a_backwards_page_range_is_rejected(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        from sqlalchemy.exc import IntegrityError

        session.add(
            DocumentChunk(
                book_id=book.id,
                text="bad",
                pages=[4],
                page_start=9,
                page_end=4,
            )
        )

        with pytest.raises(IntegrityError):
            await session.commit()

        await session.rollback()

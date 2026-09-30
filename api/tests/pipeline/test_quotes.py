import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.db.models import Book, DocumentChunk, Project
from api.pipeline import quotes
from api.pipeline.storage import store

FIXTURE = Path(__file__).parent.parent / "fixtures" / "three_page_novel.pdf"

# The fixture's real page text (api/tests/pipeline/test_render.py extracts the
# same PDF) — kept here as the ground truth these tests locate quotes against.
PAGE_1_TEXT = (
    "Chapter 1\r\nThe Meeting\r\nElizabeth had not been long at Netherfield before she"
    "\r\ndiscovered that Mr Darcy was not at all what she had\r\nbeen led to expect of "
    "him, and said so to Jane."
)
PAGE_2_TEXT = (
    "She turned the matter over in her mind for some days,\r\nand said nothing of it "
    "to her sister, nor to anyone\r\nelse at Netherfield, though the temptation was "
    "great."
)


@pytest_asyncio.fixture(autouse=True)
async def _clean_bucket() -> AsyncIterator[None]:
    yield
    await store.delete_prefix("books/")


@pytest_asyncio.fixture
async def uploaded_book(session: SQLModelAsyncSession, project: Project) -> Book:
    book_id = uuid.uuid4()
    storage_key = f"books/{book_id}/source.pdf"
    row = Book(
        id=book_id,
        project_id=project.id,
        title="Three Page Novel",
        content_hash=uuid.uuid4().hex,
        storage_key=storage_key,
        page_count=3,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    await store.put_stream(storage_key, FIXTURE, content_type="application/pdf")

    return row


async def _chunk(
    session: SQLModelAsyncSession,
    book: Book,
    *,
    text: str,
    pages: list[int],
    page_start: int,
    page_end: int,
) -> DocumentChunk:
    row = DocumentChunk(
        book_id=book.id,
        text=text,
        pages=pages,
        page_start=page_start,
        page_end=page_end,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return row


class TestExactAndWhitespaceDrift:
    async def test_an_exact_substring_locates(
        self, session: SQLModelAsyncSession, uploaded_book: Book
    ) -> None:
        chunk = await _chunk(
            session,
            uploaded_book,
            text=PAGE_1_TEXT,
            pages=[1],
            page_start=1,
            page_end=1,
        )

        span = await quotes.locate_quote(session, chunk.id, "Chapter 1")

        assert span is not None
        assert span.page == 1
        assert len(span.boxes) > 0
        assert all(box.page == 1 for box in span.boxes)

    async def test_a_quote_crossing_a_line_break_locates(
        self, session: SQLModelAsyncSession, uploaded_book: Book
    ) -> None:
        # The source has "\r\n" where a model-produced quote has a plain
        # space — this is the whitespace-normalised stage, not exact.
        chunk = await _chunk(
            session,
            uploaded_book,
            text=PAGE_1_TEXT,
            pages=[1],
            page_start=1,
            page_end=1,
        )
        quote = (
            "Elizabeth had not been long at Netherfield before she discovered "
            "that Mr Darcy was not at all what she had been led to expect of him"
        )

        span = await quotes.locate_quote(session, chunk.id, quote)

        assert span is not None
        assert span.page == 1
        assert len(span.boxes) > 0


class TestFuzzyDrift:
    async def test_a_trailing_typo_still_locates(
        self, session: SQLModelAsyncSession, uploaded_book: Book
    ) -> None:
        chunk = await _chunk(
            session,
            uploaded_book,
            text=PAGE_1_TEXT,
            pages=[1],
            page_start=1,
            page_end=1,
        )
        # One character wrong on the last word — "drift by a character or
        # two", the acceptance criterion's own phrasing.
        quote = (
            "Elizabeth had not been long at Netherfield before she discovered "
            "that Mr Darcy was not at all what she had been led to expect of hims"
        )

        span = await quotes.locate_quote(session, chunk.id, quote)

        assert span is not None
        assert span.page == 1


class TestFabricatedQuotes:
    async def test_a_fabricated_quote_never_locates(
        self, session: SQLModelAsyncSession, uploaded_book: Book
    ) -> None:
        chunk = await _chunk(
            session,
            uploaded_book,
            text=PAGE_1_TEXT,
            pages=[1],
            page_start=1,
            page_end=1,
        )
        quote = "The dragon breathed fire across the whole valley of Netherfield"

        span = await quotes.locate_quote(session, chunk.id, quote)

        assert span is None

    async def test_a_short_fabricated_quote_never_locates(
        self, session: SQLModelAsyncSession, uploaded_book: Book
    ) -> None:
        chunk = await _chunk(
            session,
            uploaded_book,
            text=PAGE_1_TEXT,
            pages=[1],
            page_start=1,
            page_end=1,
        )

        span = await quotes.locate_quote(session, chunk.id, "Zorblatt the dragon")

        assert span is None

    async def test_an_empty_quote_never_locates(
        self, session: SQLModelAsyncSession, uploaded_book: Book
    ) -> None:
        chunk = await _chunk(
            session,
            uploaded_book,
            text=PAGE_1_TEXT,
            pages=[1],
            page_start=1,
            page_end=1,
        )

        span = await quotes.locate_quote(session, chunk.id, "   ")

        assert span is None


class TestScopeAndMissingData:
    async def test_search_is_scoped_to_the_chunks_own_pages(
        self, session: SQLModelAsyncSession, uploaded_book: Book
    ) -> None:
        # A quote that genuinely exists on page 1 must not be found via a
        # chunk that only claims page 2.
        chunk = await _chunk(
            session,
            uploaded_book,
            text=PAGE_2_TEXT,
            pages=[2],
            page_start=2,
            page_end=2,
        )

        span = await quotes.locate_quote(session, chunk.id, "Chapter 1")

        assert span is None

    async def test_the_right_page_is_searched_when_pages_differ_from_chunk_text(
        self, session: SQLModelAsyncSession, uploaded_book: Book
    ) -> None:
        chunk = await _chunk(
            session,
            uploaded_book,
            text=PAGE_2_TEXT,
            pages=[2],
            page_start=2,
            page_end=2,
        )

        span = await quotes.locate_quote(session, chunk.id, "her sister")

        assert span is not None
        assert span.page == 2

    async def test_an_unknown_chunk_returns_none(
        self, session: SQLModelAsyncSession
    ) -> None:
        span = await quotes.locate_quote(session, uuid.uuid4(), "anything")

        assert span is None

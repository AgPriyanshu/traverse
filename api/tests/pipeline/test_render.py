"""Page render service (S2.6): cached image, dimensions, and text-span boxes."""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.db.engine import get_session
from api.db.models import Book, Project
from api.main import app
from api.pipeline import render
from api.pipeline.storage import store

FIXTURE = Path(__file__).parent.parent / "fixtures" / "three_page_novel.pdf"


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


@pytest_asyncio.fixture
async def uploaded_book(session: SQLModelAsyncSession, project: Project) -> Book:
    """A saved book whose ``storage_key`` points at a real three-page PDF."""
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


class TestRenderPageModule:
    async def test_a_cold_render_returns_dimensions_and_spans(
        self, uploaded_book: Book
    ) -> None:
        out = await render.render_page(
            uploaded_book.id, uploaded_book.storage_key, 1, uploaded_book.page_count
        )

        assert out.book_id == uploaded_book.id
        assert out.page == 1
        assert out.width == 612.0
        assert out.height == 792.0
        assert len(out.spans) > 0
        assert all(span.page == 1 for span in out.spans)
        # Top-left origin, unscaled PDF points: a span cannot start above the
        # page or run past its bottom edge.
        assert all(0 <= span.y <= out.height for span in out.spans)

    async def test_the_rendered_image_is_a_real_png(self, uploaded_book: Book) -> None:
        out = await render.render_page(
            uploaded_book.id, uploaded_book.storage_key, 1, uploaded_book.page_count
        )

        async with httpx.AsyncClient() as http:
            response = await http.get(out.image_url)

        assert response.status_code == 200
        assert response.content[:8] == b"\x89PNG\r\n\x1a\n"

    async def test_a_cached_render_does_not_touch_the_source_pdf(
        self, uploaded_book: Book, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        first = await render.render_page(
            uploaded_book.id, uploaded_book.storage_key, 2, uploaded_book.page_count
        )

        async def fail_if_called(key: str, dest: Path) -> None:
            raise AssertionError("cached render re-fetched the source PDF")

        monkeypatch.setattr(store, "get_object", fail_if_called)

        second = await render.render_page(
            uploaded_book.id, uploaded_book.storage_key, 2, uploaded_book.page_count
        )

        assert second.width == first.width
        assert second.height == first.height
        assert len(second.spans) == len(first.spans)

    async def test_a_page_beyond_the_known_count_is_out_of_range(
        self, uploaded_book: Book
    ) -> None:
        with pytest.raises(render.PageOutOfRangeError):
            await render.render_page(
                uploaded_book.id,
                uploaded_book.storage_key,
                99,
                uploaded_book.page_count,
            )

    async def test_page_zero_is_out_of_range(self, uploaded_book: Book) -> None:
        with pytest.raises(render.PageOutOfRangeError):
            await render.render_page(
                uploaded_book.id, uploaded_book.storage_key, 0, uploaded_book.page_count
            )

    async def test_an_unknown_page_count_defers_to_the_pdf_itself(
        self, uploaded_book: Book
    ) -> None:
        out = await render.render_page(
            uploaded_book.id, uploaded_book.storage_key, 3, None
        )

        assert out.page == 3

        with pytest.raises(render.PageOutOfRangeError):
            await render.render_page(
                uploaded_book.id, uploaded_book.storage_key, 4, None
            )


class TestRenderPageRoute:
    async def test_returns_a_page_render(
        self, client: AsyncClient, uploaded_book: Book
    ) -> None:
        response = await client.get(f"/api/books/{uploaded_book.id}/pages/1")
        body = response.json()

        assert response.status_code == 200
        assert body["book_id"] == str(uploaded_book.id)
        assert body["page"] == 1
        assert body["width"] == 612.0
        assert len(body["spans"]) > 0

    async def test_an_unknown_book_is_404(self, client: AsyncClient) -> None:
        response = await client.get(f"/api/books/{uuid.uuid4()}/pages/1")

        assert response.status_code == 404

    async def test_a_book_with_no_stored_source_is_404(
        self, client: AsyncClient, session: SQLModelAsyncSession, project: Project
    ) -> None:
        row = Book(
            project_id=project.id,
            title="Never Uploaded",
            content_hash=uuid.uuid4().hex,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)

        response = await client.get(f"/api/books/{row.id}/pages/1")

        assert response.status_code == 404

    async def test_a_page_past_the_end_is_404(
        self, client: AsyncClient, uploaded_book: Book
    ) -> None:
        response = await client.get(f"/api/books/{uploaded_book.id}/pages/99")

        assert response.status_code == 404

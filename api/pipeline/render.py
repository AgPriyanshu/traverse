"""Lazy PDF page rendering: a cached PNG plus text-span bounding boxes (S2.6).

Renders straight from the source PDF via ``pypdfium2`` rather than through
Docling — Docling's own per-page image option means re-converting the whole
book to serve one page, and a 1,000-page novel rendered eagerly is 400 MB of
PNG nobody asked for. A page is opened, rendered, and closed; nothing here
touches the chunker or its models.

Both ``pypdfium2`` and ``Pillow`` are already resolved, locked transitive
dependencies of ``docling`` (see ``uv.lock``) — no new dependency was added,
matching the precedent in ``storage.py``.
"""

import io
import json
import tempfile
from pathlib import Path
from uuid import UUID

import anyio
import pypdfium2 as pdfium

from ..contracts.api import PageRenderOut, SpanBox
from .storage import store

_RENDER_DPI = 150
_PDF_POINTS_PER_INCH = 72
_SIGNED_URL_TTL_SECONDS = 300


class PageOutOfRangeError(Exception):
    """The requested page does not exist in this book."""


def _cache_keys(book_id: UUID, page: int) -> tuple[str, str]:
    prefix = f"books/{book_id}/pages/{page}"

    return f"{prefix}.png", f"{prefix}.json"


async def _cached_render(png_key: str, meta_key: str) -> PageRenderOut | None:
    if not await store.exists(png_key):
        return None

    try:
        raw = await store.get_bytes(meta_key)
        meta = json.loads(raw)
    except Exception:  # noqa: BLE001 — any read/parse failure means "not cached"
        return None

    return PageRenderOut(
        book_id=meta["book_id"],
        page=meta["page"],
        image_url=store.presigned_get(png_key, expires_in=_SIGNED_URL_TTL_SECONDS),
        width=meta["width"],
        height=meta["height"],
        spans=[SpanBox(**span) for span in meta["spans"]],
    )


def _render_sync(
    pdf_path: Path, page_index: int
) -> tuple[bytes, float, float, list[SpanBox]]:
    document = pdfium.PdfDocument(pdf_path)
    try:
        if page_index >= len(document):
            raise PageOutOfRangeError(f"document has {len(document)} pages")

        pdf_page = document[page_index]
        try:
            width, height = pdf_page.get_size()

            bitmap = pdf_page.render(scale=_RENDER_DPI / _PDF_POINTS_PER_INCH)
            try:
                buffer = io.BytesIO()
                bitmap.to_pil().save(buffer, format="PNG")
                png_bytes = buffer.getvalue()
            finally:
                bitmap.close()

            text_page = pdf_page.get_textpage()
            try:
                # ``count_rects`` must run before ``get_rect`` is meaningful
                # (pypdfium2's own calling convention).
                rect_count = text_page.count_rects(0, -1)
                spans = []
                for index in range(rect_count):
                    # PDF canvas units, origin bottom-left; the contract is
                    # top-left (agreed with fe1, HANDOFF.md), so flip here
                    # once rather than pushing the conversion onto every
                    # consumer.
                    left, bottom, right, top = text_page.get_rect(index)
                    spans.append(
                        SpanBox(
                            page=page_index + 1,
                            x=left,
                            y=height - top,
                            width=right - left,
                            height=top - bottom,
                        )
                    )
            finally:
                text_page.close()
        finally:
            pdf_page.close()
    finally:
        document.close()

    return png_bytes, width, height, spans


async def render_page(
    book_id: UUID, storage_key: str, page: int, page_count: int | None
) -> PageRenderOut:
    """Return a page's rendered image, dimensions and text-span boxes.

    Cached at ``books/{book_id}/pages/{page}.png`` (image) and a same-named
    ``.json`` sidecar (dimensions and spans) on first request, so a
    re-request never re-touches the source PDF.

    Args:
        book_id: The book the page belongs to.
        storage_key: Where the source PDF lives in object storage.
        page: 1-indexed page number.
        page_count: The book's known page count, if parsing has finished.
            ``None`` skips the cheap pre-check and lets the PDF itself decide
            — a page render does not require the parse stage to have run.

    Returns:
        The presigned image URL, page dimensions, and every text span, all
        in top-left-origin PDF points, unscaled (agreed with fe1).

    Raises:
        PageOutOfRangeError: If ``page`` is not a real page of this book.
        StorageError: If the source PDF or a cached render cannot be reached.
    """
    if page < 1 or (page_count is not None and page > page_count):
        raise PageOutOfRangeError(f"book {book_id} has no page {page}")

    png_key, meta_key = _cache_keys(book_id, page)

    cached = await _cached_render(png_key, meta_key)
    if cached is not None:
        return cached

    handle = await anyio.to_thread.run_sync(
        lambda: tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)  # noqa: SIM115
    )
    temp_path = Path(handle.name)
    await anyio.to_thread.run_sync(handle.close)

    try:
        await store.get_object(storage_key, temp_path)
        png_bytes, width, height, spans = await anyio.to_thread.run_sync(
            _render_sync, temp_path, page - 1
        )
    finally:
        await anyio.to_thread.run_sync(temp_path.unlink, True)

    await store.put_bytes(png_key, png_bytes, content_type="image/png")
    metadata = {
        "book_id": str(book_id),
        "page": page,
        "width": width,
        "height": height,
        "spans": [span.model_dump() for span in spans],
    }
    await store.put_bytes(
        meta_key, json.dumps(metadata).encode(), content_type="application/json"
    )

    return PageRenderOut(
        book_id=book_id,
        page=page,
        image_url=store.presigned_get(png_key, expires_in=_SIGNED_URL_TTL_SECONDS),
        width=width,
        height=height,
        spans=spans,
    )

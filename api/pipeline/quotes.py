"""Quote-span location for citation highlighting (S6.8).

Given a chunk and a quote pulled from it by the generation stage, find the
page and bounding boxes to highlight — reusing the page-render span
machinery from S2.6 (:mod:`api.pipeline.render`) rather than a second PDF
text-extraction path.

A quote that cannot be located is **not** a citation (query-path.md): the
caller must drop it rather than point at the wrong span, which is worse than
no citation at all. This module only ever returns a real, located span or
``None`` — it never guesses.
"""

import difflib
import re
from pathlib import Path
from uuid import UUID

import anyio
import pypdfium2 as pdfium
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import SpanBox
from . import repository
from .render import local_copy

# Below this, a coincidental short substring is too likely to be a false
# positive; the exact/normalised stages already cover short genuine quotes.
_MIN_FUZZY_QUOTE_CHARS = 20
_FUZZY_MATCH_RATIO = 0.85

_WHITESPACE_RE = re.compile(r"\s+")
_CURLY_APOSTROPHES = str.maketrans({"‘": "'", "’": "'"})
_CURLY_QUOTES = str.maketrans({"“": '"', "”": '"'})


class PageSpan(BaseModel):
    """A located quote: which page, and the boxes to highlight on it."""

    page: int
    boxes: list[SpanBox]


def _normalize_with_mapping(raw: str) -> tuple[str, list[int]]:
    """Fold whitespace and curly punctuation, keeping a normalised->raw index map.

    A model's quote drifts from the source by whitespace (a line-wrapped
    ``"\\r\\n"`` where the citation has a single space) and smart-quote
    variants, never by real content — this stage absorbs exactly that drift,
    nothing more.
    """
    folded = raw.translate(_CURLY_APOSTROPHES).translate(_CURLY_QUOTES)

    normalized_chars: list[str] = []
    mapping: list[int] = []
    prev_was_space = True  # leading whitespace collapses away, like ``.strip()``

    for index, char in enumerate(folded):
        if char.isspace():
            if prev_was_space:
                continue
            normalized_chars.append(" ")
            mapping.append(index)
            prev_was_space = True
        else:
            normalized_chars.append(char.lower())
            mapping.append(index)
            prev_was_space = False

    while normalized_chars and normalized_chars[-1] == " ":
        normalized_chars.pop()
        mapping.pop()

    return "".join(normalized_chars), mapping


def _normalize_quote(quote: str) -> str:
    folded = quote.translate(_CURLY_APOSTROPHES).translate(_CURLY_QUOTES)

    return _WHITESPACE_RE.sub(" ", folded).strip().lower()


def _find_raw_span(raw_text: str, quote: str) -> tuple[int, int] | None:
    """Return ``(start, count)`` in ``raw_text``'s own indices, or ``None``.

    Exact and normalised-whitespace matches are unbounded — the text is
    genuinely there. The fuzzy stage is deliberately conservative (see the
    module-level thresholds): it exists for a dropped character or an
    ellipsis-vs-dash difference, not to rescue a fabricated quote.
    """
    if quote in raw_text:
        start = raw_text.index(quote)

        return start, len(quote)

    normalized_raw, mapping = _normalize_with_mapping(raw_text)
    normalized_quote = _normalize_quote(quote)
    if not normalized_quote:
        return None

    index = normalized_raw.find(normalized_quote)
    if index != -1:
        raw_start = mapping[index]
        raw_end = mapping[index + len(normalized_quote) - 1]

        return raw_start, raw_end - raw_start + 1

    if len(normalized_quote) < _MIN_FUZZY_QUOTE_CHARS:
        return None

    matcher = difflib.SequenceMatcher(
        None, normalized_raw, normalized_quote, autojunk=False
    )
    match = matcher.find_longest_match(0, len(normalized_raw), 0, len(normalized_quote))
    required = max(
        _MIN_FUZZY_QUOTE_CHARS, round(_FUZZY_MATCH_RATIO * len(normalized_quote))
    )
    if match.size < required:
        return None

    raw_start = mapping[match.a]
    raw_end = mapping[match.a + match.size - 1]

    return raw_start, raw_end - raw_start + 1


def _rects_for_span(
    text_page: pdfium.PdfTextPage,
    page_number: int,
    height: float,
    start: int,
    count: int,
) -> list[SpanBox]:
    rect_count = text_page.count_rects(start, count)
    boxes = []

    for index in range(rect_count):
        left, bottom, right, top = text_page.get_rect(index)
        boxes.append(
            SpanBox(
                page=page_number,
                x=left,
                y=height - top,
                width=right - left,
                height=top - bottom,
            )
        )

    return boxes


def _candidate_pages(pages: list[int], page_start: int, page_end: int) -> list[int]:
    if pages:
        ordered = sorted(set(pages))

        return ordered

    return list(range(page_start, page_end + 1))


def _locate_sync(
    pdf_path: Path, quote: str, candidate_pages: list[int]
) -> tuple[int, list[SpanBox]] | None:
    document = pdfium.PdfDocument(pdf_path)
    try:
        for page_number in candidate_pages:
            page_index = page_number - 1
            if page_index < 0 or page_index >= len(document):
                continue

            pdf_page = document[page_index]
            try:
                _, height = pdf_page.get_size()
                text_page = pdf_page.get_textpage()
                try:
                    raw_text = text_page.get_text_range(0, -1)
                    span = _find_raw_span(raw_text, quote)
                    if span is None:
                        continue

                    start, count = span
                    boxes = _rects_for_span(
                        text_page, page_number, height, start, count
                    )
                    if not boxes:
                        continue

                    return page_number, boxes
                finally:
                    text_page.close()
            finally:
                pdf_page.close()
    finally:
        document.close()

    return None


async def locate_quote(
    session: SQLModelAsyncSession, chunk_id: UUID, quote: str
) -> PageSpan | None:
    """Find a quote's page and bounding boxes within its own chunk.

    Args:
        session: An open database session.
        chunk_id: The chunk the quote was cited against.
        quote: The exact or near-exact text to locate.

    Returns:
        The page and highlight boxes, or ``None`` if the quote cannot be
        found on any page the chunk spans — callers must drop the citation
        in that case rather than cite an unlocated page.
    """
    quote = quote.strip()
    if not quote:
        return None

    located = await repository.get_chunk_with_book(session, chunk_id)
    if located is None:
        return None

    chunk, book = located
    if not book.storage_key:
        return None

    candidate_pages = _candidate_pages(chunk.pages, chunk.page_start, chunk.page_end)

    async with local_copy(book.storage_key) as pdf_path:
        result = await anyio.to_thread.run_sync(
            _locate_sync, pdf_path, quote, candidate_pages
        )

    if result is None:
        return None

    page_number, boxes = result

    return PageSpan(page=page_number, boxes=boxes)

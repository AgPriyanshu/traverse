"""Citation construction shared by the graph-derived and narrative render paths.

Two call sites need slightly different strictness, so this module exposes
both rather than picking one:

- Graph-derived classes (character/relationship lookup, path, aggregation,
  series arc) cite ``RelationEvidence``/``CharacterMention`` quotes that were
  already checked to appear in their chunk at extraction time (the relation
  validator's substring check, ``api/AGENTS.md`` domain invariants). If
  ``locate_quote`` cannot re-find the span — most likely a storage hiccup in
  this environment, not a fabricated quote — falling back to the evidence
  row's own recorded page range is still a real, previously-verified
  citation, just without an exact highlight box.
- ``narrative``'s citations quote a freshly generated sentence against a
  chunk, which is unverified until this check runs — there ``locate_quote``
  failing must drop the citation outright (``api/query/grounding.py``).
"""

from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import CitationOut

QUOTE_MAX_CHARS = 400


async def build_citation_from_evidence(
    session: SQLModelAsyncSession,
    *,
    chunk_id: UUID,
    book_id: UUID,
    book_title: str | None,
    series_order: int | None,
    chapter_no: int | None,
    page_start: int,
    page_end: int,
    quote: str,
) -> CitationOut:
    """Build a citation from an already-validated evidence quote.

    Never drops the citation: the quote was already proven to appear in its
    chunk when the relation was extracted, so this only refines the page down
    to the exact span when the source PDF is reachable, and otherwise falls
    back to the evidence's own recorded page range.
    """
    quote = quote[:QUOTE_MAX_CHARS]
    page = page_start

    try:
        from ..pipeline.quotes import locate_quote

        located = await locate_quote(session, chunk_id, quote)
        if located is not None:
            page = located.page
    except Exception:
        pass

    citation = CitationOut(
        book_id=book_id,
        book_title=book_title,
        series_order=series_order,
        page_start=page if page else page_start,
        page_end=page if page else page_end,
        chapter_no=chapter_no,
        quote=quote,
        chunk_id=chunk_id,
    )

    return citation

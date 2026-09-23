"""Dense and lexical arms of hybrid retrieval, and the query embedding.

Kept separate from ``hybrid.py`` per the repository convention (``api/AGENTS.md``):
views and fusion logic call this, they do not build queries inline.
"""

from functools import lru_cache
from uuid import UUID

from sentence_transformers import SentenceTransformer
from sqlalchemy import func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..config.settings import settings
from ..db.models.chunk_model import DocumentChunk
from ..db.models.project_model import Book, Chapter
from ..pipeline.chunking import resolve_device

DENSE_LIMIT = 50
LEXICAL_LIMIT = 50


@lru_cache(maxsize=1)
def embedding_model() -> SentenceTransformer:
    """Return the process-wide BGE-M3 handle, loading it on first use.

    Public (not ``_``-prefixed) because ``graph/similarity.py``'s mention
    clustering (S3.8) reuses this exact handle rather than loading a second
    copy — two ``SentenceTransformer`` instances is exactly the kind of
    thing that doubles resident memory for no reason (BRANCH.md §9).
    """
    # No explicit cache_folder: same as DocumentChunker's loader
    # (api/pipeline/chunking.py), letting it resolve the standard HF cache
    # rather than settings.models_cache_dir, which is a container path
    # ("/models") that does not exist on a bare host.
    return SentenceTransformer(
        settings.embedding_model_id, device=resolve_device(settings.embedding_device)
    )


def embed_query(text: str) -> list[float]:
    """Embed a search query with the same model and normalisation as chunks.

    An un-normalised query vector against normalised chunk vectors returns
    wrong neighbours rather than an error, so this mirrors
    ``DocumentChunker.embed_texts`` exactly.
    """
    vector = embedding_model().encode(
        [text], normalize_embeddings=True, show_progress_bar=False
    )[0]

    return vector.tolist()


def _reading_position_filter(
    statement, *, limit_book_order: int | None, limit_chapter: int | None
):
    """Restrict a chunk query to a reading position, series-position style.

    A chunk with no chapter (front matter, before the first heading) is never
    a spoiler and always passes; one whose chapter is unknown because the
    book itself has no ``series_order`` is treated the same way — the caller
    is asking about a standalone book, position ``(1, chapter)`` in
    everything else this codebase does, but ``Book.series_order`` is
    nullable, so the comparison must fall through to "no restriction" rather
    than exclude every chunk in a standalone book.
    """
    if limit_book_order is None:
        return statement

    chapter_number = (
        select(Chapter.number)
        .where(Chapter.id == DocumentChunk.chapter_id)
        .scalar_subquery()
    )

    return statement.where(
        or_(
            Book.series_order.is_(None),
            Book.series_order < limit_book_order,
            (Book.series_order == limit_book_order)
            & (
                chapter_number.is_(None)
                if limit_chapter is None
                else chapter_number <= limit_chapter
            ),
        )
    )


async def dense_search(
    session: SQLModelAsyncSession,
    *,
    project_id: UUID,
    query_embedding: list[float],
    book_id: UUID | None = None,
    character_ids: list[UUID] | None = None,
    limit_book_order: int | None = None,
    limit_chapter: int | None = None,
    limit: int = DENSE_LIMIT,
) -> list[tuple[DocumentChunk, float]]:
    """Return the ``limit`` chunks closest to ``query_embedding`` by cosine.

    Args:
        session: An open database session.
        project_id: Scopes the search to one project.
        query_embedding: A normalised BGE-M3 vector, from ``embed_query``.
        book_id: Restrict to one book.
        character_ids: Present for the Sprint 6 graph-constrained retrieval
            hook; not yet backed by a real filter (chunk-to-character linkage
            lands in S4), so it is accepted and ignored rather than rejected.
        limit_book_order: Reading position — book. ``None`` means no limit.
        limit_chapter: Reading position — chapter within that book.
        limit: Top-N to return.

    Returns:
        ``(chunk, similarity)`` pairs, most similar first. Similarity is
        ``1 - cosine_distance``, in ``[-1, 1]`` but practically ``[0, 1]``
        for normalised text embeddings.
    """
    del character_ids  # See docstring — accepted now, wired in S4.

    distance = DocumentChunk.text_embedding.cosine_distance(query_embedding)
    similarity = (1 - distance).label("similarity")

    statement = (
        select(DocumentChunk, similarity)
        .join(Book, Book.id == DocumentChunk.book_id)
        .where(Book.project_id == project_id)
        .where(DocumentChunk.text_embedding.is_not(None))
    )

    if book_id is not None:
        statement = statement.where(DocumentChunk.book_id == book_id)

    statement = _reading_position_filter(
        statement, limit_book_order=limit_book_order, limit_chapter=limit_chapter
    )
    statement = statement.order_by(distance).limit(limit)

    result = await session.exec(statement)

    return [(chunk, score) for chunk, score in result.all()]


async def lexical_search(
    session: SQLModelAsyncSession,
    *,
    project_id: UUID,
    query: str,
    book_id: UUID | None = None,
    character_ids: list[UUID] | None = None,
    limit_book_order: int | None = None,
    limit_chapter: int | None = None,
    limit: int = LEXICAL_LIMIT,
) -> list[tuple[DocumentChunk, float]]:
    """Return the ``limit`` chunks best matching ``query`` by ``ts_rank_cd``.

    Args:
        session: An open database session.
        project_id: Scopes the search to one project.
        query: Free-text query, parsed with ``websearch_to_tsquery``.
        book_id: Restrict to one book.
        character_ids: See ``dense_search`` — accepted, not yet wired.
        limit_book_order: Reading position — book. ``None`` means no limit.
        limit_chapter: Reading position — chapter within that book.
        limit: Top-N to return.

    Returns:
        ``(chunk, rank)`` pairs, best match first. A chunk whose ``tsvector``
        does not match the query at all is never returned — ``ts_rank_cd`` of
        a non-match is ``0``, not absent, so the query filters on the match
        rather than on the rank.
    """
    del character_ids

    tsquery = func.websearch_to_tsquery("english", query)
    rank = func.ts_rank_cd(DocumentChunk.tsv, tsquery).label("rank")

    statement = (
        select(DocumentChunk, rank)
        .join(Book, Book.id == DocumentChunk.book_id)
        .where(Book.project_id == project_id)
        .where(DocumentChunk.tsv.op("@@")(tsquery))
    )

    if book_id is not None:
        statement = statement.where(DocumentChunk.book_id == book_id)

    statement = _reading_position_filter(
        statement, limit_book_order=limit_book_order, limit_chapter=limit_chapter
    )
    statement = statement.order_by(rank.desc()).limit(limit)

    result = await session.exec(statement)

    return [(chunk, score) for chunk, score in result.all()]

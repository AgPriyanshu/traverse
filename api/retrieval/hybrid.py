"""Hybrid retrieval: dense (pgvector) + lexical (``ts_rank_cd``), fused by RRF.

Reciprocal rank fusion, not score normalisation — a cosine similarity and a
``ts_rank_cd`` score are not commensurable, and normalising two incommensurable
scores onto a shared scale is where hybrid search usually goes wrong (PRD F4.1).
"""

from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import ChunkOut, SearchResultOut
from ..db.models.chunk_model import DocumentChunk
from . import repository

RRF_K = 60


def _to_chunk_out(
    chunk: DocumentChunk, *, dense_score: float | None, lexical_score: float | None
) -> ChunkOut:
    return ChunkOut(
        id=chunk.id,
        book_id=chunk.book_id,
        chapter_id=chunk.chapter_id,
        text=chunk.text,
        pages=list(chunk.pages or []),
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        token_count=chunk.token_count,
        dense_score=dense_score,
        lexical_score=lexical_score,
    )


def _reciprocal_rank_fusion(
    dense: list[tuple[DocumentChunk, float]],
    lexical: list[tuple[DocumentChunk, float]],
) -> list[tuple[UUID, float, DocumentChunk, float | None, float | None]]:
    """Fuse two ranked arms by reciprocal rank, ``k=60``.

    A chunk in both arms sums both arms' ``1 / (k + rank)`` terms — the
    two raw scores never touch each other, only their ranks do.

    Returns:
        ``(chunk_id, rrf_score, chunk, dense_score, lexical_score)`` tuples,
        highest ``rrf_score`` first.
    """
    chunks: dict[UUID, DocumentChunk] = {}
    dense_scores: dict[UUID, float] = {}
    lexical_scores: dict[UUID, float] = {}
    rrf_scores: dict[UUID, float] = {}

    for rank, (chunk, score) in enumerate(dense, start=1):
        chunks[chunk.id] = chunk
        dense_scores[chunk.id] = score
        rrf_scores[chunk.id] = rrf_scores.get(chunk.id, 0.0) + 1.0 / (RRF_K + rank)

    for rank, (chunk, score) in enumerate(lexical, start=1):
        chunks[chunk.id] = chunk
        lexical_scores[chunk.id] = score
        rrf_scores[chunk.id] = rrf_scores.get(chunk.id, 0.0) + 1.0 / (RRF_K + rank)

    fused = [
        (
            chunk_id,
            rrf_score,
            chunks[chunk_id],
            dense_scores.get(chunk_id),
            lexical_scores.get(chunk_id),
        )
        for chunk_id, rrf_score in rrf_scores.items()
    ]
    fused.sort(key=lambda item: item[1], reverse=True)

    return fused


async def hybrid_search(
    session: SQLModelAsyncSession,
    *,
    project_id: UUID,
    query: str,
    book_id: UUID | None = None,
    character_ids: list[UUID] | None = None,
    limit: int = 20,
    limit_book_order: int | None = None,
    limit_chapter: int | None = None,
    rerank: bool | None = None,
) -> SearchResultOut:
    """Run both retrieval arms and fuse them with reciprocal rank fusion.

    Args:
        session: An open database session.
        project_id: Scopes the search to one project.
        query: Free-text search query.
        book_id: Restrict to one book. ``None`` searches the whole project.
        character_ids: The Sprint 4 graph-constrained retrieval hook — plumbed
            through now (query-path.md), not yet backed by a filter.
        limit: Chunks to return after fusion.
        limit_book_order: Reading position — book. ``None`` means no limit
            and must be an explicit choice at the call site (the Sprint 8
            spoiler hook — PRD F8, query-path.md).
        limit_chapter: Reading position — chapter within that book.
        rerank: Force the cross-encoder reranker on or off for this call,
            overriding ``settings.reranker_enabled``. ``None`` defers to the
            setting (S2.10).

    Returns:
        Fused, ranked chunks with both component scores populated where the
        arm that found them ran; ``tier`` is unset until the Sprint 6 router
        assigns one.
    """
    # Deferred: keeps the reranker's cross-encoder import (and model load)
    # out of every call that never uses it.
    from . import rerank as rerank_module

    query_embedding = repository.embed_query(query)

    dense_results = await repository.dense_search(
        session,
        project_id=project_id,
        query_embedding=query_embedding,
        book_id=book_id,
        character_ids=character_ids,
        limit_book_order=limit_book_order,
        limit_chapter=limit_chapter,
    )
    lexical_results = await repository.lexical_search(
        session,
        project_id=project_id,
        query=query,
        book_id=book_id,
        character_ids=character_ids,
        limit_book_order=limit_book_order,
        limit_chapter=limit_chapter,
    )

    fused = _reciprocal_rank_fusion(dense_results, lexical_results)

    use_rerank = rerank_module.reranker_enabled() if rerank is None else rerank
    if use_rerank and fused:
        fused = rerank_module.rerank(query, fused)

    top = fused[:limit]
    chunks = [
        _to_chunk_out(chunk, dense_score=dense_score, lexical_score=lexical_score)
        for _chunk_id, _rrf_score, chunk, dense_score, lexical_score in top
    ]

    return SearchResultOut(chunks=chunks)

from enum import StrEnum
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import ChunkOut, SearchResultOut
from ..db.models.chunk_model import DocumentChunk
from ..query.scope import ReadingScope
from . import repository

RRF_K = 60


class RetrievalMode(StrEnum):
    """The retrieval ablation axis (PRD Appendix A): each step adds one arm.

    ``vector_only -> +BM25 -> +rerank -> +graph_constrained`` is a
    progression, not four independent choices — each value below runs
    everything to its left plus one more thing. Values match
    ``AblationConfig.retrieval_mode`` (``api/contracts/api.py``) exactly, so
    an eval cell's config constructs one of these directly, no translation
    table to drift out of sync (S8.2, F6.3).
    """

    VECTOR_ONLY = "vector_only"
    BM25 = "bm25"
    RERANK = "rerank"
    GRAPH_CONSTRAINED = "graph_constrained"


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
    scope: ReadingScope,
    book_id: UUID | None = None,
    character_ids: list[UUID] | None = None,
    limit: int = 20,
    rerank: bool | None = None,
    mode: RetrievalMode | None = None,
) -> SearchResultOut:
    """Run the retrieval arms ``mode`` calls for and fuse them with RRF.

    Args:
        session: An open database session.
        project_id: Scopes the search to one project.
        query: Free-text search query.
        scope: The reader's position. ``ReadingScope.unlimited()`` for no
            restriction — never a default, an explicit choice at the call
            site (S8.1, PRD F4.5, query-path.md).
        book_id: Restrict to one book. ``None`` searches the whole project.
        character_ids: S6.3's graph-constrained retrieval filter — restricts
            both arms to chunks mentioning at least one of these characters.
            ``None`` searches the whole project, unconstrained. Ignored
            (treated as ``None``) below ``RetrievalMode.GRAPH_CONSTRAINED``,
            since a lower mode is measuring retrieval without the graph
            constraint on purpose.
        limit: Chunks to return after fusion.
        rerank: Force the cross-encoder reranker on or off for this call,
            overriding ``settings.reranker_enabled``. ``None`` defers to the
            setting (S2.10). Ignored when ``mode`` is given — the mode
            already says whether rerank runs (S8.2).
        mode: The Sprint 8 ablation switch (PRD Appendix A) — which arms to
            run. ``None`` is the pre-S8.2 default: both arms, RRF-fused,
            reranked per ``rerank``/the setting, honouring ``character_ids``
            exactly as before. Equivalent to ``GRAPH_CONSTRAINED`` when
            ``character_ids`` is given, to ``RERANK`` otherwise — never a
            behaviour change for a caller that does not pass it.

    Returns:
        Fused, ranked chunks with both component scores populated where the
        arm that found them ran. ``tier`` is ``"graph_constrained"`` when
        ``character_ids`` was given, else ``"unconstrained"`` — the caller
        (``api/query/retrieval.py``) is what decides whether a constrained
        search's empty result should fall back to an unconstrained one, and
        logs which tier actually answered.
    """
    # Deferred: keeps the reranker's cross-encoder import (and model load)
    # out of every call that never uses it.
    from . import rerank as rerank_module

    effective_character_ids = (
        character_ids
        if mode is None or mode is RetrievalMode.GRAPH_CONSTRAINED
        else None
    )

    query_embedding = repository.embed_query(query)

    dense_results = await repository.dense_search(
        session,
        project_id=project_id,
        query_embedding=query_embedding,
        scope=scope,
        book_id=book_id,
        character_ids=effective_character_ids,
    )
    lexical_results: list[tuple[DocumentChunk, float]] = []
    if mode is not RetrievalMode.VECTOR_ONLY:
        lexical_results = await repository.lexical_search(
            session,
            project_id=project_id,
            query=query,
            scope=scope,
            book_id=book_id,
            character_ids=effective_character_ids,
        )

    fused = _reciprocal_rank_fusion(dense_results, lexical_results)

    if mode is None:
        use_rerank = rerank_module.reranker_enabled() if rerank is None else rerank
    else:
        use_rerank = mode in (RetrievalMode.RERANK, RetrievalMode.GRAPH_CONSTRAINED)
    if use_rerank and fused:
        fused = rerank_module.rerank(query, fused)

    top = fused[:limit]
    chunks = [
        _to_chunk_out(chunk, dense_score=dense_score, lexical_score=lexical_score)
        for _chunk_id, _rrf_score, chunk, dense_score, lexical_score in top
    ]

    tier = "graph_constrained" if effective_character_ids else "unconstrained"

    return SearchResultOut(chunks=chunks, tier=tier)

"""Graph-constrained retrieval for the narrative query class (S6.3, PRD F4.2).

Order matters (``query-path.md``): resolve names to characters, search within
the chunks those characters were actually mentioned in, and fall back to an
unconstrained project-wide search only when the constrained set is empty.
Whole-project vector search is the last resort, never the first move.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import ChunkOut
from ..retrieval import hybrid_search

NARRATIVE_RETRIEVAL_LIMIT = 12


@dataclass
class RetrievalResult:
    """What answered the question, and how — logged for the Sprint 8 ablation."""

    tier: str
    chunks: list[ChunkOut]


async def retrieve_for_narrative(
    session: SQLModelAsyncSession,
    *,
    project_id: UUID,
    question: str,
    character_ids: list[UUID],
    limit_book_order: int | None,
    limit_chapter: int | None,
) -> RetrievalResult:
    """Run graph-constrained retrieval, falling back to unconstrained search.

    Args:
        session: An open database session.
        project_id: Scopes the search to one project.
        question: The free-text question, used as the retrieval query.
        character_ids: Characters already resolved from the question. Empty
            when the question named nobody the resolver could match — the
            search then starts unconstrained rather than constrained to
            nothing, which would return zero results by construction.
        limit_book_order: Reading position — book. ``None`` means no limit.
        limit_chapter: Reading position — chapter within that book.

    Returns:
        The chunks to generate from, and which tier answered:
        ``"graph_constrained"`` (found within the resolved characters'
        mentions), ``"unconstrained"`` (fell back to whole-project search, or
        no characters were resolved to constrain by), or ``"none"`` (neither
        arm found anything).
    """
    if character_ids:
        constrained = await hybrid_search(
            session,
            project_id=project_id,
            query=question,
            character_ids=character_ids,
            limit=NARRATIVE_RETRIEVAL_LIMIT,
            limit_book_order=limit_book_order,
            limit_chapter=limit_chapter,
        )
        if constrained.chunks:
            return RetrievalResult(tier="graph_constrained", chunks=constrained.chunks)

    unconstrained = await hybrid_search(
        session,
        project_id=project_id,
        query=question,
        character_ids=None,
        limit=NARRATIVE_RETRIEVAL_LIMIT,
        limit_book_order=limit_book_order,
        limit_chapter=limit_chapter,
    )
    tier = "unconstrained" if unconstrained.chunks else "none"

    return RetrievalResult(tier=tier, chunks=unconstrained.chunks)

from dataclasses import dataclass
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import ChunkOut
from ..retrieval import RetrievalMode, hybrid_search
from .scope import ReadingScope

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
    scope: ReadingScope,
    mode: RetrievalMode | None = None,
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
        scope: The reader's position. ``ReadingScope.unlimited()`` for no
            restriction — never a default, an explicit choice at the call
            site (S8.1, PRD F4.5).
        mode: The Sprint 8 retrieval ablation switch (F6.3). ``None`` is the
            recommended production behaviour: graph-constrained first,
            falling back to unconstrained. Any value below
            ``RetrievalMode.GRAPH_CONSTRAINED`` measures that arm in
            isolation on purpose, so the two-tier fallback is skipped
            entirely rather than silently reintroducing the constraint it is
            meant to hold fixed.

    Returns:
        The chunks to generate from, and which tier answered:
        ``"graph_constrained"`` (found within the resolved characters'
        mentions), ``"unconstrained"`` (fell back to whole-project search, or
        no characters were resolved to constrain by), ``mode.value`` (a
        non-``None``, below-``GRAPH_CONSTRAINED`` mode, whether or not it
        found anything — there is no fallback tier to measure separately),
        or ``"none"`` (neither arm found anything with the default mode).
    """
    if mode is not None and mode is not RetrievalMode.GRAPH_CONSTRAINED:
        result = await hybrid_search(
            session,
            project_id=project_id,
            query=question,
            scope=scope,
            character_ids=None,
            limit=NARRATIVE_RETRIEVAL_LIMIT,
            mode=mode,
        )

        return RetrievalResult(tier=mode.value, chunks=result.chunks)

    if character_ids:
        constrained = await hybrid_search(
            session,
            project_id=project_id,
            query=question,
            scope=scope,
            character_ids=character_ids,
            limit=NARRATIVE_RETRIEVAL_LIMIT,
            mode=mode,
        )
        if constrained.chunks:
            return RetrievalResult(tier="graph_constrained", chunks=constrained.chunks)

    unconstrained = await hybrid_search(
        session,
        project_id=project_id,
        query=question,
        scope=scope,
        character_ids=None,
        limit=NARRATIVE_RETRIEVAL_LIMIT,
        mode=mode,
    )
    tier = "unconstrained" if unconstrained.chunks else "none"

    return RetrievalResult(tier=tier, chunks=unconstrained.chunks)

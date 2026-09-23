"""The relationship graph. Owned by backend engineer 2."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import (
    EvidenceOut,
    GraphOut,
    GraphPathOut,
    OntologyOut,
    RelationArcOut,
)
from ..contracts.enums import RelationFamily
from ..db.engine import get_session
from ..graph import ontology, queries, repository

router = APIRouter(tags=["graph"])


@router.get("/graph/ontology", response_model=OntologyOut)
async def get_ontology() -> OntologyOut:
    """Return the predicate registry: every predicate, family, inverse and symmetry.

    Served from ``api/graph/ontology.yaml``, so adding a predicate there is
    enough to change this response — the frontend's edge-family colour mapping
    and filter controls are generated from it.
    """
    return ontology.to_contract()


@router.get("/projects/{project_id}/graph", response_model=GraphOut)
async def get_graph(
    project_id: UUID,
    book_id: UUID | None = Query(
        default=None, description="A slice of the standing graph"
    ),
    families: list[RelationFamily] | None = Query(default=None),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    limit_book_order: int | None = Query(default=None),
    limit_chapter: int | None = Query(default=None),
    session: SQLModelAsyncSession = Depends(get_session),
) -> GraphOut:
    """Return the project's character graph, filtered.

    Raises:
        HTTPException: 404 when the project does not exist.
    """
    if not await repository.project_exists(session, project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    graph = await queries.get_graph(
        session,
        project_id,
        book_id=book_id,
        families=families,
        min_confidence=min_confidence,
        limit_book_order=limit_book_order,
        limit_chapter=limit_chapter,
    )

    return graph


@router.get("/characters/{character_id}/neighbourhood", response_model=GraphOut)
async def get_neighbourhood(
    character_id: UUID, depth: int = Query(default=1, ge=1, le=2)
) -> GraphOut:
    """Return the subgraph within ``depth`` hops of a character.

    Raises:
        HTTPException: 404 when the character is not in the graph.
    """
    graph = await queries.get_neighbourhood(character_id, depth)
    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )

    return graph


@router.get("/relations/arc", response_model=RelationArcOut)
async def get_arc(
    a: UUID, b: UUID, session: SQLModelAsyncSession = Depends(get_session)
) -> RelationArcOut:
    """Return the ordered states of one pair, a single element if unchanged."""
    arc = await repository.relation_arc(session, a, b)

    return arc


@router.get("/relations/{relation_id}/evidence", response_model=list[EvidenceOut])
async def get_evidence(
    relation_id: UUID,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: SQLModelAsyncSession = Depends(get_session),
) -> list[EvidenceOut]:
    """Return a relation's quotes and pages, chapter-ordered and paginated.

    Raises:
        HTTPException: 404 when the relation does not exist.
    """
    evidence = await repository.list_evidence(
        session, relation_id, limit=limit, offset=offset
    )
    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Relation not found"
        )

    return evidence


@router.get("/graph/path", response_model=GraphPathOut)
async def get_path(
    from_id: UUID = Query(alias="from"),
    to_id: UUID = Query(alias="to"),
    max_hops: int = Query(default=4, ge=1, le=4),
    session: SQLModelAsyncSession = Depends(get_session),
) -> GraphPathOut:
    """Return the shortest relation chain between two characters, capped at 4 hops."""
    path = await queries.shortest_path(session, from_id, to_id, max_hops)

    return path

"""The relationship graph. Owned by backend engineer 2."""

from uuid import UUID

from fastapi import APIRouter, Query

from ..contracts.api import (
    EvidenceOut,
    GraphOut,
    GraphPathOut,
    OntologyOut,
    RelationArcOut,
)
from ..contracts.enums import RelationFamily
from ._stub import not_implemented

router = APIRouter(tags=["graph"])
OWNER = "be2"


@router.get("/graph/ontology", response_model=OntologyOut)
async def get_ontology() -> OntologyOut:
    not_implemented(OWNER, "S1.7")


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
) -> GraphOut:
    not_implemented(OWNER, "S1.7 / S4.7")


@router.get("/characters/{character_id}/neighbourhood", response_model=GraphOut)
async def get_neighbourhood(
    character_id: UUID, depth: int = Query(default=1, ge=1, le=2)
) -> GraphOut:
    not_implemented(OWNER, "S4.7")


@router.get("/relations/{relation_id}/evidence", response_model=list[EvidenceOut])
async def get_evidence(
    relation_id: UUID, limit: int = Query(default=20, le=200), offset: int = 0
) -> list[EvidenceOut]:
    not_implemented(OWNER, "S4.7")


@router.get("/relations/arc", response_model=RelationArcOut)
async def get_arc(a: UUID, b: UUID) -> RelationArcOut:
    not_implemented(OWNER, "S4.4 / S5.6")


@router.get("/graph/path", response_model=GraphPathOut)
async def get_path(
    from_id: UUID = Query(alias="from"),
    to_id: UUID = Query(alias="to"),
    max_hops: int = Query(default=4, ge=1, le=4),
) -> GraphPathOut:
    not_implemented(OWNER, "S4.7")

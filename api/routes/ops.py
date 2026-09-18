"""Health, cost and pipeline telemetry. Owned by devops engineer 1."""

from uuid import UUID

from fastapi import APIRouter, Query

from ..contracts.api import (
    DeadLetterOut,
    HealthOut,
    MetricsOut,
    RoutingPolicyOut,
)
from ..contracts.pipeline import IngestionRunOut
from ..ops import gather_health
from ._stub import not_implemented

router = APIRouter(tags=["ops"])
OWNER = "do1"


@router.get("/health", response_model=HealthOut, tags=["ops"])
async def health() -> HealthOut:
    """Liveness plus per-dependency status.

    Real probes as of S1.12 (``api/ops/probes.py``, do1) — concurrent, 5s
    timeout each. ``llm`` never gates the overall status: the default profile
    has no GPU (PRD NFR-deploy).
    """
    return await gather_health()


@router.get("/ops/metrics", response_model=MetricsOut)
async def metrics(book_id: UUID | None = Query(default=None)) -> MetricsOut:
    not_implemented(OWNER, "S2.17 / S9.1")


@router.get("/ops/pipeline/runs", response_model=list[IngestionRunOut])
async def pipeline_runs(
    book_id: UUID | None = Query(default=None), limit: int = Query(default=50, le=200)
) -> list[IngestionRunOut]:
    not_implemented(OWNER, "S2.18")


@router.get("/ops/pipeline/dead-letter", response_model=list[DeadLetterOut])
async def dead_letter() -> list[DeadLetterOut]:
    not_implemented(OWNER, "S2.18")


@router.get("/ops/routing-policy", response_model=RoutingPolicyOut)
async def get_routing_policy() -> RoutingPolicyOut:
    not_implemented(OWNER, "S9.6")


@router.put("/ops/routing-policy", response_model=RoutingPolicyOut)
async def set_routing_policy(body: RoutingPolicyOut) -> RoutingPolicyOut:
    not_implemented(OWNER, "S9.6")

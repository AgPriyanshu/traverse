"""Health, cost and pipeline telemetry. Owned by devops engineer 1."""

from uuid import UUID

from fastapi import APIRouter, Query

from ..contracts.api import (
    DeadLetterOut,
    DependencyHealth,
    HealthOut,
    MetricsOut,
    RoutingPolicyOut,
)
from ..contracts.pipeline import IngestionRunOut
from ._stub import not_implemented

router = APIRouter(tags=["ops"])
OWNER = "do1"


@router.get("/health", response_model=HealthOut, tags=["ops"])
async def health() -> HealthOut:
    """Liveness plus per-dependency status.

    Implemented shallow at the freeze so compose has something to gate on;
    do1 fills in the real dependency probes in S1.12.
    """
    return HealthOut(
        status="degraded",
        dependencies=[
            DependencyHealth(
                name="api", ok=True, detail="contract freeze — handlers pending"
            ),
            DependencyHealth(name="db", ok=False, detail="not probed yet (S1.12)"),
            DependencyHealth(name="neo4j", ok=False, detail="not probed yet (S1.12)"),
            DependencyHealth(name="broker", ok=False, detail="not probed yet (S1.12)"),
            DependencyHealth(name="llm", ok=False, detail="not probed yet (S1.12)"),
        ],
    )


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

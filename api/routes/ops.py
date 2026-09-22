"""Health, cost and pipeline telemetry. Owned by devops engineer 1."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import (
    DeadLetterOut,
    HealthOut,
    MetricsOut,
    RoutingPolicyOut,
)
from ..contracts.pipeline import IngestionRunOut
from ..db.engine import get_session
from ..ops import gather_health, pipeline_status
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
async def metrics(
    book_id: UUID | None = Query(default=None),
    session: SQLModelAsyncSession = Depends(get_session),
) -> MetricsOut:
    """Per-stage cost and timing (S2.17). ``prefix_cache_hit_rate`` waits on S9.1."""
    return await pipeline_status.get_metrics(session, book_id=book_id)


@router.get("/ops/pipeline/runs", response_model=list[IngestionRunOut])
async def pipeline_runs(
    book_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    session: SQLModelAsyncSession = Depends(get_session),
) -> list[IngestionRunOut]:
    """Most recent ingestion runs, newest first, each with its stages and trace."""
    return await pipeline_status.list_runs(session, book_id=book_id, limit=limit)


@router.get("/ops/pipeline/dead-letter", response_model=list[DeadLetterOut])
async def dead_letter(
    session: SQLModelAsyncSession = Depends(get_session),
) -> list[DeadLetterOut]:
    """Every book whose latest run has a stage currently `failed`."""
    return await pipeline_status.list_dead_letters(session)


@router.get("/ops/routing-policy", response_model=RoutingPolicyOut)
async def get_routing_policy() -> RoutingPolicyOut:
    not_implemented(OWNER, "S9.6")


@router.put("/ops/routing-policy", response_model=RoutingPolicyOut)
async def set_routing_policy(body: RoutingPolicyOut) -> RoutingPolicyOut:
    not_implemented(OWNER, "S9.6")

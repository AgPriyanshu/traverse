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
from ..ops.extraction_cost import ExtractionCostOut, compute_extraction_cost
from ..ops.extraction_quality import ExtractionQualityOut, compute_extraction_quality
from ..ops.relation_cost import RelationCostOut, compute_relation_cost
from ..ops.relation_quality import RelationQualityOut, compute_relation_quality
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
    """Per-stage cost and timing (S2.17). ``prefix_cache_hit_rate`` is live from
    vLLM as of S3.15 (``api/ops/vllm_metrics.py``) when running local inference."""
    return await pipeline_status.get_metrics(session, book_id=book_id)


@router.get("/ops/extraction-quality", response_model=ExtractionQualityOut)
async def extraction_quality(
    book_id: UUID = Query(...),
    session: SQLModelAsyncSession = Depends(get_session),
) -> ExtractionQualityOut:
    """Roster P/R/F1, B3, tier accuracy, rejection precision (S3.14).

    Informational only this sprint — a regression gate lands in Sprint 8
    (F6.4). Returns ``gold_available=False`` for any book without a labelled
    gold set (``eval/gold/**``); today that is every book except Pride and
    Prejudice and Wuthering Heights (S3.13).
    """
    return await compute_extraction_quality(session, book_id)


@router.get("/ops/extraction-cost", response_model=ExtractionCostOut)
async def extraction_cost(
    book_id: UUID = Query(...),
    session: SQLModelAsyncSession = Depends(get_session),
) -> ExtractionCostOut:
    """Tokens, cost at both rates, and wall clock/100 pages for pass 1 (S3.15).

    Prefix-cache hit rate and KV-cache usage are read live from vLLM when
    ``INFERENCE_MODE=local``; ``None`` under ``INFERENCE_MODE=api`` since
    there is no local cache to report on.
    """
    return await compute_extraction_cost(session, book_id)


@router.get("/ops/relation-quality", response_model=RelationQualityOut)
async def relation_quality(
    book_id: UUID = Query(...),
    session: SQLModelAsyncSession = Depends(get_session),
) -> RelationQualityOut:
    """Per-predicate P/R/F1, spurious and direction rates, temporal arcs (S4.14).

    Also reports the evidence-free edge count, which must be 0 whether or not
    the book has gold relations. ``gold_available=False`` for an unlabelled book.
    """
    return await compute_relation_quality(session, book_id)


@router.get("/ops/relation-cost", response_model=RelationCostOut)
async def relation_cost(
    book_id: UUID = Query(...),
    session: SQLModelAsyncSession = Depends(get_session),
) -> RelationCostOut:
    """Pass-2 tokens, chunks skipped, wall clock, USD and cache hit rate (S4.15).

    ``prefix_cache_alert`` is set when a measured hit rate is below 80%.
    """
    return await compute_relation_cost(session, book_id)


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

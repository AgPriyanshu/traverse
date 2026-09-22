"""Extraction cost and throughput breakdown (S3.15).

Extends S2.17's per-stage cost accounting (``api/ops/metrics.py``,
``api/ops/pipeline_status.py``) with the LLM-heavy-stage detail
plans/sprint-3/devops-1.md S3.15 asks for: wall clock normalised per 100
pages (so books of different lengths compare), USD at both the
local-amortised rate actually paid and a hosted-API comparison rate, and
vLLM's own prefix-cache/KV-cache gauges.

Kept as a separate response model rather than added to the frozen
``MetricsOut`` (``api/contracts/api.py``) -- that file is orchestrator-owned
as of the S3 freeze; see ``plans/sprint-3/SCR.md`` SCR-2 for the follow-up to
fold these fields into ``MetricsOut``/``StageCost`` once the freeze can take
them. ``GET /ops/metrics``'s own ``prefix_cache_hit_rate`` (already a frozen
field) is populated live in the meantime -- see
``api/ops/pipeline_status.py``.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..config import settings
from ..contracts.enums import InferenceMode, StageName
from ..db.models import Book, IngestionRun, IngestionStage
from .metrics import estimate_api_equivalent_cost_usd, wall_clock_ms_per_100_pages
from .vllm_metrics import fetch_vllm_cache_stats

# The LLM-heavy stages S3.15 asks to extend cost/throughput reporting for.
EXTRACTION_STAGES = (StageName.EXTRACT_CHARACTERS, StageName.RESOLVE_ALIASES)


class ExtractionStageCost(BaseModel):
    stage: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd_local: float = 0.0
    cost_usd_api_equivalent: float | None = None
    duration_ms: int = 0
    wall_clock_ms_per_100_pages: float | None = None


class ExtractionCostOut(BaseModel):
    """``GET /ops/extraction-cost`` response -- S3.15."""

    book_id: UUID
    page_count: int | None = None
    stages: list[ExtractionStageCost] = Field(default_factory=list)
    total_cost_usd_local: float = 0.0
    total_cost_usd_api_equivalent: float | None = None
    prefix_cache_hit_rate: float | None = None
    gpu_kv_cache_usage_pct: float | None = None


async def compute_extraction_cost(
    session: SQLModelAsyncSession, book_id: UUID
) -> ExtractionCostOut:
    """The character-extraction stages' cost/throughput for a book's latest run."""
    book = await session.get(Book, book_id)
    page_count = book.page_count if book else None

    latest_run = (
        select(IngestionRun.id)
        .where(IngestionRun.book_id == book_id)  # type: ignore[arg-type]
        .order_by(IngestionRun.created_at.desc())  # type: ignore[union-attr]
        .limit(1)
    )
    run_id = (await session.execute(latest_run)).scalars().first()

    rows: list[IngestionStage] = []
    if run_id is not None:
        statement = select(IngestionStage).where(
            IngestionStage.run_id == run_id,  # type: ignore[arg-type]
            IngestionStage.stage.in_(EXTRACTION_STAGES),  # type: ignore[attr-defined]
        )
        rows = list((await session.execute(statement)).scalars().all())

    by_name = {row.stage: row for row in rows}
    stages: list[ExtractionStageCost] = []
    for stage_name in EXTRACTION_STAGES:
        row = by_name.get(stage_name)
        if row is None:
            continue

        input_tokens = row.input_tokens or 0
        output_tokens = row.output_tokens or 0
        duration_ms = row.duration_ms or 0
        stages.append(
            ExtractionStageCost(
                stage=stage_name.value,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd_local=row.cost_usd or 0.0,
                cost_usd_api_equivalent=estimate_api_equivalent_cost_usd(
                    settings.llm_model, input_tokens, output_tokens
                ),
                duration_ms=duration_ms,
                wall_clock_ms_per_100_pages=wall_clock_ms_per_100_pages(
                    duration_ms, page_count
                ),
            )
        )

    cache_stats = None
    if settings.inference_mode == InferenceMode.LOCAL:
        cache_stats = await fetch_vllm_cache_stats(settings.vllm_base_url)

    total_local = sum(s.cost_usd_local for s in stages)
    api_costs = [
        s.cost_usd_api_equivalent
        for s in stages
        if s.cost_usd_api_equivalent is not None
    ]
    total_api = sum(api_costs) if api_costs else None

    return ExtractionCostOut(
        book_id=book_id,
        page_count=page_count,
        stages=stages,
        total_cost_usd_local=total_local,
        total_cost_usd_api_equivalent=total_api,
        prefix_cache_hit_rate=cache_stats.prefix_cache_hit_rate
        if cache_stats
        else None,
        gpu_kv_cache_usage_pct=cache_stats.gpu_kv_cache_usage_pct
        if cache_stats
        else None,
    )

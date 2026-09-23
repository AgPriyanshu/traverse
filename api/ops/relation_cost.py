"""Pass-2 cost and prefix-cache reporting (S4.15).

Pass 2 (``relations.extract``) is the most expensive stage in the system and
PRD section 5.2's cost argument rests on vLLM's prefix cache serving the
byte-identical roster prefix. This reports, per book, tokens, chunks processed
versus skipped by the prefilter, wall clock, USD at both rates, and the cache
hit rate with an alert flag when it drops below the threshold.

Kept as a locally defined response model, like ``extraction_cost.py``, because
``api/contracts/api.py`` is frozen (see ``plans/sprint-4/SCR.md``).
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..config import settings
from ..contracts.enums import InferenceMode, StageName
from ..db.models import Book, DocumentChunk, IngestionRun, IngestionStage
from .metrics import estimate_api_equivalent_cost_usd, wall_clock_ms_per_100_pages
from .vllm_metrics import fetch_vllm_cache_stats

PASS2_STAGES = (
    StageName.EXTRACT_RELATIONS,
    StageName.AGGREGATE_RELATIONS,
    StageName.UPSERT_GRAPH,
)

PREFIX_CACHE_ALERT_THRESHOLD = 0.80


class RelationStageCost(BaseModel):
    stage: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd_local: float = 0.0
    cost_usd_api_equivalent: float | None = None
    duration_ms: int = 0


class RelationCostOut(BaseModel):
    book_id: UUID
    page_count: int | None = None
    stages: list[RelationStageCost] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost_usd_local: float = 0.0
    total_cost_usd_api_equivalent: float | None = None
    wall_clock_ms: int = 0
    wall_clock_ms_per_100_pages: float | None = None

    chunks_total: int | None = None
    chunks_processed: int | None = None
    chunks_skipped: int | None = None
    prefilter_skip_ratio: float | None = None

    prefix_cache_hit_rate: float | None = None
    prefix_cache_alert_threshold: float = PREFIX_CACHE_ALERT_THRESHOLD
    prefix_cache_alert: bool = False


def cache_alert(hit_rate: float | None) -> bool:
    """True only when a rate was measured and it is below the threshold.

    An unmeasured rate (``INFERENCE_MODE=api``, vLLM down) is not an alert: it
    is reported as ``None`` instead, so a missing signal is not confused with a
    cache regression.
    """
    return hit_rate is not None and hit_rate < PREFIX_CACHE_ALERT_THRESHOLD


async def compute_relation_cost(
    session: SQLModelAsyncSession, book_id: UUID
) -> RelationCostOut:
    """The pass-2 stages' cost and throughput for a book's latest run.

    ``chunks_processed`` is the ``rows_written`` of ``relations.extract``:
    the stage's own count of chunks it sent to the model, and therefore what
    the prefilter (S4.10) did not skip.
    """
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
            IngestionStage.stage.in_(PASS2_STAGES),  # type: ignore[attr-defined]
        )
        rows = list((await session.execute(statement)).scalars().all())

    by_name = {row.stage: row for row in rows}
    stages: list[RelationStageCost] = []
    for stage_name in PASS2_STAGES:
        row = by_name.get(stage_name)
        if row is None:
            continue
        input_tokens = row.input_tokens or 0
        output_tokens = row.output_tokens or 0
        stages.append(
            RelationStageCost(
                stage=stage_name.value,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd_local=row.cost_usd or 0.0,
                cost_usd_api_equivalent=estimate_api_equivalent_cost_usd(
                    settings.llm_model, input_tokens, output_tokens
                ),
                duration_ms=row.duration_ms or 0,
            )
        )

    chunks_total = (
        await session.execute(
            select(func.count(DocumentChunk.id)).where(  # type: ignore[arg-type]
                DocumentChunk.book_id == book_id  # type: ignore[arg-type]
            )
        )
    ).scalar_one()
    extract_row = by_name.get(StageName.EXTRACT_RELATIONS)
    processed = extract_row.rows_written if extract_row else None
    skipped = None
    skip_ratio = None
    if processed is not None and chunks_total:
        skipped = max(chunks_total - processed, 0)
        skip_ratio = skipped / chunks_total

    hit_rate = None
    if settings.inference_mode == InferenceMode.LOCAL:
        stats = await fetch_vllm_cache_stats(settings.vllm_base_url)
        hit_rate = stats.prefix_cache_hit_rate if stats else None

    api_costs = [
        s.cost_usd_api_equivalent
        for s in stages
        if s.cost_usd_api_equivalent is not None
    ]
    wall_clock = sum(s.duration_ms for s in stages)

    return RelationCostOut(
        book_id=book_id,
        page_count=page_count,
        stages=stages,
        input_tokens=sum(s.input_tokens for s in stages),
        output_tokens=sum(s.output_tokens for s in stages),
        total_cost_usd_local=sum(s.cost_usd_local for s in stages),
        total_cost_usd_api_equivalent=sum(api_costs) if api_costs else None,
        wall_clock_ms=wall_clock,
        wall_clock_ms_per_100_pages=wall_clock_ms_per_100_pages(wall_clock, page_count),
        chunks_total=int(chunks_total),
        chunks_processed=processed,
        chunks_skipped=skipped,
        prefilter_skip_ratio=skip_ratio,
        prefix_cache_hit_rate=hit_rate,
        prefix_cache_alert=cache_alert(hit_rate),
    )

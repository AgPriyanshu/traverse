from __future__ import annotations

from uuid import UUID

from eval.latency_metrics import (
    P95_BUDGET_MS,
    TTFT_BUDGET_MS,
    budget_violations,
    sample_from_query_log_row,
    summarize,
)
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..db.models import QueryLog


class PercentileSetOut(BaseModel):
    p50: float | None
    p95: float | None
    p99: float | None
    n: int


class QueryLatencyOut(BaseModel):
    """``GET /ops/query-latency`` response -- S6.15."""

    project_id: UUID
    sample_count: int
    total_ms: PercentileSetOut
    ttft_ms: PercentileSetOut
    per_stage_ms: dict[str, PercentileSetOut]
    avg_cost_usd: float | None
    p95_within_budget: bool | None
    ttft_p95_within_budget: bool | None
    p95_budget_ms: int = P95_BUDGET_MS
    ttft_budget_ms: int = TTFT_BUDGET_MS
    violations: list[str]


def _pct_out(pct) -> PercentileSetOut:
    return PercentileSetOut(p50=pct.p50, p95=pct.p95, p99=pct.p99, n=pct.n)


async def compute_query_latency(
    session: SQLModelAsyncSession, project_id: UUID, *, limit: int = 500
) -> QueryLatencyOut:
    """Score the most recent ``limit`` queries logged for ``project_id``."""
    result = await session.execute(
        select(QueryLog.latency_ms, QueryLog.cost_usd)
        .where(QueryLog.project_id == project_id)
        .order_by(QueryLog.created_at.desc())
        .limit(limit)
    )
    rows = result.all()

    samples = [
        sample
        for latency_ms, cost_usd in rows
        if (
            sample := sample_from_query_log_row(
                {"latency_ms": latency_ms, "cost_usd": cost_usd}
            )
        )
        is not None
    ]
    summary = summarize(samples)

    return QueryLatencyOut(
        project_id=project_id,
        sample_count=summary.sample_count,
        total_ms=_pct_out(summary.total),
        ttft_ms=_pct_out(summary.ttft),
        per_stage_ms={stage: _pct_out(pct) for stage, pct in summary.per_stage.items()},
        avg_cost_usd=summary.avg_cost_usd,
        p95_within_budget=summary.p95_within_budget,
        ttft_p95_within_budget=summary.ttft_p95_within_budget,
        violations=budget_violations(summary),
    )

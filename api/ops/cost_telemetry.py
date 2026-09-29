"""Rolling cost telemetry: by stage, by purpose, and per query (S9.1, F7.1).

``api/ops/metrics.py`` turns a token count into a dollar figure and
``api/ops/pipeline_status.py::get_metrics`` reads ``IngestionStage`` for one
book's latest run. This module is the broader aggregate PRD F7.1 also asks
for: cost across every book and query in a rolling window, broken out by
stage (so pass 2's dominance is visible, not lumped) and by purpose (so a
frontier ``judge`` call is not hidden inside a stage total), plus the two
headline ratios -- cost per book ingested and cost per query answered.

``CostSnapshot`` (migration 0014) persists one window's rollup so the
dashboard has history to plot without re-aggregating raw rows on every
request; ``compute_cost_breakdown`` always computes live from
``IngestionStage``/``QueryLog`` and ``save_cost_snapshot`` is a separate,
explicit write -- a read never has the side effect of writing history.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import CostBreakdown
from ..contracts.enums import LLMPurpose, StageName
from ..db.models import CostSnapshot, IngestionRun, IngestionStage, QueryLog

# IngestionStage has no purpose column of its own -- a stage is either pure
# I/O (parse, chunk, embed, upsert) or exactly one LLM purpose. This mapping
# is do1's own convention for splitting cost by purpose (F7.1); it is not a
# frozen contract, so a future stage should be added here rather than left to
# fall through `_STAGE_PURPOSE.get(stage)` returning ``None``.
_STAGE_PURPOSE: dict[StageName, LLMPurpose] = {
    StageName.SEGMENT_CHAPTERS: LLMPurpose.CHAPTER_CLASSIFY,
    StageName.EXTRACT_CHARACTERS: LLMPurpose.CHARACTER_EXTRACT,
    StageName.RESOLVE_ALIASES: LLMPurpose.ADJUDICATE,
    StageName.RECONCILE_CHARACTERS: LLMPurpose.ADJUDICATE,
    StageName.EXTRACT_RELATIONS: LLMPurpose.RELATION_EXTRACT,
    StageName.AGGREGATE_RELATIONS: LLMPurpose.ADJUDICATE,
}

DAILY_WINDOW = timedelta(days=1)
MONTHLY_WINDOW = timedelta(days=30)


def rolling_window(*, days: int) -> tuple[datetime, datetime]:
    """``[now - days, now)``, both timezone-aware -- the "rolling" in F7.1."""
    end = datetime.now(UTC)
    return end - timedelta(days=days), end


async def compute_cost_breakdown(
    session: SQLModelAsyncSession,
    *,
    window_start: datetime,
    window_end: datetime,
) -> CostBreakdown:
    """Cost across every book/query whose row falls in ``[window_start, window_end)``.

    Ingestion cost is grouped by ``IngestionStage.stage``; a purpose total is
    derived from `_STAGE_PURPOSE` and query cost is added to ``answer``
    (``QueryLog`` carries no purpose of its own, only a route). A stage or
    query with no cost recorded (``cost_usd is None`` -- API-mode routing not
    yet wired, or a call that predates cost accounting) contributes 0, not a
    missing key, so ``by_stage``/``by_purpose`` always cover every stage that
    ran in the window.
    """
    stage_rows = (
        await session.execute(
            select(IngestionStage, IngestionRun.book_id)
            .join(IngestionRun, IngestionStage.run_id == IngestionRun.id)  # type: ignore[arg-type]
            .where(IngestionStage.created_at >= window_start)  # type: ignore[operator]
            .where(IngestionStage.created_at < window_end)  # type: ignore[operator]
        )
    ).all()

    query_rows = (
        await session.execute(
            select(QueryLog.cost_usd)
            .where(QueryLog.created_at >= window_start)  # type: ignore[operator]
            .where(QueryLog.created_at < window_end)  # type: ignore[operator]
        )
    ).all()

    by_stage: dict[str, float] = defaultdict(float)
    by_purpose: dict[str, float] = defaultdict(float)
    book_ids: set = set()

    for stage_row, book_id in stage_rows:
        cost = stage_row.cost_usd or 0.0
        by_stage[stage_row.stage.value] += cost
        purpose = _STAGE_PURPOSE.get(stage_row.stage)
        if purpose is not None:
            by_purpose[purpose.value] += cost
        book_ids.add(book_id)

    query_cost_total = 0.0
    for (cost_usd,) in query_rows:
        cost = cost_usd or 0.0
        query_cost_total += cost
        by_purpose[LLMPurpose.ANSWER.value] += cost

    total_cost_usd = sum(by_stage.values()) + query_cost_total

    return CostBreakdown(
        window_start=window_start,
        window_end=window_end,
        total_cost_usd=total_cost_usd,
        by_stage=dict(by_stage),
        by_purpose=dict(by_purpose),
        query_count=len(query_rows),
        book_count=len(book_ids),
    )


def cost_per_book(breakdown: CostBreakdown) -> float | None:
    """Average ingestion cost per book in the window, ``None`` if none ingested."""
    if breakdown.book_count == 0:
        return None
    ingestion_cost = breakdown.total_cost_usd - breakdown.by_purpose.get(
        LLMPurpose.ANSWER.value, 0.0
    )
    return ingestion_cost / breakdown.book_count


def cost_per_query(breakdown: CostBreakdown) -> float | None:
    """Average cost per query answered in the window, ``None`` if none answered."""
    if breakdown.query_count == 0:
        return None
    return breakdown.by_purpose.get(LLMPurpose.ANSWER.value, 0.0) / breakdown.query_count


async def save_cost_snapshot(
    session: SQLModelAsyncSession, breakdown: CostBreakdown
) -> CostSnapshot:
    """Persist one window's rollup so the dashboard has history to chart."""
    row = CostSnapshot(
        window_start=breakdown.window_start,
        window_end=breakdown.window_end,
        total_cost_usd=breakdown.total_cost_usd,
        by_stage=breakdown.by_stage,
        by_purpose=breakdown.by_purpose,
        query_count=breakdown.query_count,
        book_count=breakdown.book_count,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_cost_snapshots(
    session: SQLModelAsyncSession, *, limit: int = 90
) -> list[CostSnapshot]:
    """Most recent stored snapshots, newest first -- the rolling-spend chart."""
    result = await session.execute(
        select(CostSnapshot).order_by(CostSnapshot.window_end.desc()).limit(limit)  # type: ignore[union-attr]
    )
    return list(result.scalars().all())

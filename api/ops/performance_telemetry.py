from __future__ import annotations

from uuid import UUID

from eval.latency_metrics import PercentileSet, percentile
from pydantic import BaseModel
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..config import settings
from ..contracts.enums import InferenceMode
from ..db.models import Book, IngestionRun, IngestionStage
from .metrics import wall_clock_ms_per_100_pages
from .vllm_metrics import fetch_vllm_cache_stats


class PercentileSetOut(BaseModel):
    p50: float | None
    p95: float | None
    p99: float | None
    n: int


def _out(pct: PercentileSet) -> PercentileSetOut:
    return PercentileSetOut(p50=pct.p50, p95=pct.p95, p99=pct.p99, n=pct.n)


class ThroughputOut(BaseModel):
    book_id: UUID
    pages_per_minute: float | None


class QueueDepthOut(BaseModel):
    """Best-effort, from ``celery inspect`` -- not a broker-side backlog count.

    ``active`` + ``reserved`` + ``scheduled`` is what the workers this host
    can see are currently holding, not what is still sitting unclaimed in
    RabbitMQ (that needs the management HTTP API, which is not wired up --
    see HANDOFF.md). ``None`` for any field the broker did not answer within
    the inspect timeout, same convention as ``api/ops/healthcheck.py``.
    """

    active: int | None
    reserved: int | None
    scheduled: int | None
    reachable: bool


class PerformanceOut(BaseModel):
    """``GET /ops/performance`` response -- S9.2."""

    book_id: UUID | None
    stage_latency_ms: dict[str, PercentileSetOut]
    ingestion_throughput: list[ThroughputOut]
    prefix_cache_hit_rate: float | None
    gpu_kv_cache_usage_pct: float | None
    queue_depth: QueueDepthOut
    inference_mode: str


INSPECT_TIMEOUT_S = 2.0


async def _stage_latency_percentiles(
    session: SQLModelAsyncSession, *, book_id: UUID | None
) -> dict[str, PercentileSetOut]:
    """p50/p95/p99 wall clock per stage, across however many runs match.

    Scoped to one book's runs when ``book_id`` is given (every run, not just
    the latest -- a single run has too few points to make a percentile
    meaningful), otherwise across every run ever recorded.
    """
    statement = select(IngestionStage.stage, IngestionStage.duration_ms).where(
        IngestionStage.duration_ms.is_not(None)  # type: ignore[union-attr]
    )
    if book_id is not None:
        statement = statement.join(
            IngestionRun,
            IngestionStage.run_id == IngestionRun.id,  # type: ignore[arg-type]
        ).where(IngestionRun.book_id == book_id)  # type: ignore[arg-type]

    rows = (await session.execute(statement)).all()

    by_stage: dict[str, list[float]] = {}
    for stage, duration_ms in rows:
        by_stage.setdefault(stage.value, []).append(float(duration_ms))

    return {
        stage: _out(
            PercentileSet(
                p50=percentile(values, 0.50),
                p95=percentile(values, 0.95),
                p99=percentile(values, 0.99),
                n=len(values),
            )
        )
        for stage, values in by_stage.items()
    }


async def _ingestion_throughput(
    session: SQLModelAsyncSession, *, book_id: UUID | None
) -> list[ThroughputOut]:
    """Pages/min for the parse stage of each matching book's latest run.

    Parse is the one stage whose duration is dominated by page count rather
    than roster or chunk size, so it is the throughput number worth charting
    -- the others are cost-per-token stories, already covered by
    ``/ops/cost-breakdown``.
    """
    from ..contracts.enums import StageName

    statement = (
        select(IngestionStage.duration_ms, IngestionRun.book_id, Book.page_count)
        .join(IngestionRun, IngestionStage.run_id == IngestionRun.id)  # type: ignore[arg-type]
        .join(Book, Book.id == IngestionRun.book_id)  # type: ignore[arg-type]
        .where(IngestionStage.stage == StageName.PARSE_AND_CHUNK)
        .where(IngestionStage.duration_ms.is_not(None))  # type: ignore[union-attr]
    )
    if book_id is not None:
        statement = statement.where(IngestionRun.book_id == book_id)  # type: ignore[arg-type]

    rows = (await session.execute(statement)).all()

    out = []
    for duration_ms, run_book_id, page_count in rows:
        ms_per_100 = wall_clock_ms_per_100_pages(duration_ms, page_count)
        pages_per_minute = 100 / (ms_per_100 / 60_000) if ms_per_100 else None
        out.append(
            ThroughputOut(book_id=run_book_id, pages_per_minute=pages_per_minute)
        )
    return out


def _queue_depth() -> QueueDepthOut:
    """Best-effort snapshot from ``celery inspect`` -- never raises.

    A broker the operator hasn't started (local dev, most unit tests) must
    not turn ``/ops/performance`` into a 500; ``reachable=False`` says so
    explicitly rather than a silently-zeroed depth pretending the queue is
    empty.
    """
    try:
        from ..tasks import celery_app

        inspect = celery_app.control.inspect(timeout=INSPECT_TIMEOUT_S)
        active = inspect.active() or None
        reserved = inspect.reserved() or None
        scheduled = inspect.scheduled() or None
    except Exception:
        return QueueDepthOut(
            active=None, reserved=None, scheduled=None, reachable=False
        )

    if active is None and reserved is None and scheduled is None:
        return QueueDepthOut(
            active=None, reserved=None, scheduled=None, reachable=False
        )

    def _count(value: dict | None) -> int | None:
        if value is None:
            return None
        return sum(len(tasks) for tasks in value.values())

    return QueueDepthOut(
        active=_count(active),
        reserved=_count(reserved),
        scheduled=_count(scheduled),
        reachable=True,
    )


async def compute_performance(
    session: SQLModelAsyncSession, *, book_id: UUID | None = None
) -> PerformanceOut:
    stage_latency_ms = await _stage_latency_percentiles(session, book_id=book_id)
    throughput = await _ingestion_throughput(session, book_id=book_id)
    queue_depth = _queue_depth()

    cache_stats = None
    if settings.inference_mode == InferenceMode.LOCAL:
        cache_stats = await fetch_vllm_cache_stats(settings.vllm_base_url)

    hit_rate = cache_stats.prefix_cache_hit_rate if cache_stats else None
    kv_usage = cache_stats.gpu_kv_cache_usage_pct if cache_stats else None

    return PerformanceOut(
        book_id=book_id,
        stage_latency_ms=stage_latency_ms,
        ingestion_throughput=throughput,
        prefix_cache_hit_rate=hit_rate,
        gpu_kv_cache_usage_pct=kv_usage,
        queue_depth=queue_depth,
        inference_mode=settings.inference_mode.value,
    )

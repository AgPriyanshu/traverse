"""Run history, dead-letter and cost queries. Owned by devops engineer 1.

Read-only reporting over the tables `api/workers/stages.py` (be1, S1) already
writes — nothing here mutates `ingestion_run` / `ingestion_stage`.
"""

from collections import defaultdict
from uuid import UUID

from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..config import settings
from ..contracts.api import DeadLetterOut, MetricsOut, StageCost
from ..contracts.enums import InferenceMode, StageName, StageState
from ..contracts.pipeline import IngestionRunOut, StageStatus
from ..db.models import Book, IngestionRun, IngestionStage
from .vllm_metrics import fetch_vllm_cache_stats

_STAGE_ORDER = {name: index for index, name in enumerate(StageName)}


def _sorted_by_pipeline_order(rows: list[IngestionStage]) -> list[IngestionStage]:
    return sorted(rows, key=lambda row: _STAGE_ORDER.get(row.stage, len(_STAGE_ORDER)))


def _to_stage_status(row: IngestionStage) -> StageStatus:
    return StageStatus(
        stage=row.stage,
        state=row.state,
        attempt=row.attempt,
        started_at=row.started_at,
        finished_at=row.finished_at,
        duration_ms=row.duration_ms,
        error=row.error_message,
    )


async def list_runs(
    session: SQLModelAsyncSession, *, book_id: UUID | None = None, limit: int = 50
) -> list[IngestionRunOut]:
    """The most recent ingestion runs, newest first, each with its stages.

    One link in the dead-letter view (devops-1.md S2.17): every run here
    carries the `trace_url` a failed stage's Langfuse trace lives behind.
    """
    statement = (
        select(IngestionRun).order_by(IngestionRun.created_at.desc()).limit(limit)
    )  # type: ignore[union-attr]
    if book_id is not None:
        statement = statement.where(IngestionRun.book_id == book_id)  # type: ignore[arg-type]

    runs = list((await session.execute(statement)).scalars().all())
    if not runs:
        return []

    run_ids = [run.id for run in runs]
    stage_statement = select(IngestionStage).where(IngestionStage.run_id.in_(run_ids))  # type: ignore[attr-defined]
    stage_rows = list((await session.execute(stage_statement)).scalars().all())

    stages_by_run: dict[UUID, list[IngestionStage]] = defaultdict(list)
    for row in stage_rows:
        stages_by_run[row.run_id].append(row)

    return [
        IngestionRunOut(
            run_id=run.id,
            book_id=run.book_id,
            stages=[
                _to_stage_status(row)
                for row in _sorted_by_pipeline_order(stages_by_run.get(run.id, []))
            ],
            trace_url=run.trace_url,
        )
        for run in runs
    ]


async def list_dead_letters(session: SQLModelAsyncSession) -> list[DeadLetterOut]:
    """Every book whose *latest* run has a stage sitting in `failed`.

    Mirrors `api.pipeline.repository.derive_book_status`'s own definition of
    a failed book: a stage row is upserted in place on retry (one row per
    run+stage, `attempt` bumped), so a currently-`failed` row on the latest
    run — not any row that was ever failed — is what a human still needs to
    act on.
    """
    latest_run = (
        select(
            IngestionRun.book_id,
            func.max(IngestionRun.created_at).label("created_at"),
        )
        .group_by(IngestionRun.book_id)
        .subquery()
    )

    statement = (
        select(IngestionStage, IngestionRun, Book)
        .join(IngestionRun, IngestionStage.run_id == IngestionRun.id)  # type: ignore[arg-type]
        .join(
            latest_run,
            (IngestionRun.book_id == latest_run.c.book_id)
            & (IngestionRun.created_at == latest_run.c.created_at),
        )
        .join(Book, Book.id == IngestionRun.book_id)  # type: ignore[arg-type]
        .where(IngestionStage.state == StageState.FAILED)
        .order_by(IngestionRun.created_at.desc())  # type: ignore[union-attr]
    )

    rows = (await session.execute(statement)).all()

    return [
        DeadLetterOut(
            book_id=book.id,
            book_title=book.title,
            stage=stage.stage.value,
            error_class=stage.error_class,
            error_message=stage.error_message,
            attempts=stage.attempt,
            trace_url=run.trace_url,
        )
        for stage, run, book in rows
    ]


async def get_metrics(
    session: SQLModelAsyncSession, *, book_id: UUID | None = None
) -> MetricsOut:
    """Per-stage cost and timing.

    With `book_id`, the breakdown for that book's latest run (matching
    `GET /books/{id}/status`'s own notion of "latest"). Without it, totals
    summed across every run ever recorded — the F7.1 dashboard's feed.

    `prefix_cache_hit_rate` is left `None`: it needs a vLLM metrics
    integration this sprint does not build (Sprint 9).
    """
    if book_id is not None:
        latest = (
            select(IngestionRun.id)
            .where(IngestionRun.book_id == book_id)  # type: ignore[arg-type]
            .order_by(IngestionRun.created_at.desc())  # type: ignore[union-attr]
            .limit(1)
        )
        run_id = (await session.execute(latest)).scalars().first()
        if run_id is None:
            return MetricsOut(book_id=book_id)

        statement = select(IngestionStage).where(IngestionStage.run_id == run_id)  # type: ignore[arg-type]
        rows = _sorted_by_pipeline_order(
            list((await session.execute(statement)).scalars().all())
        )
        stages = [
            StageCost(
                stage=row.stage.value,
                input_tokens=row.input_tokens or 0,
                output_tokens=row.output_tokens or 0,
                cost_usd=row.cost_usd or 0.0,
                duration_ms=row.duration_ms or 0,
            )
            for row in rows
        ]
    else:
        rows = list((await session.execute(select(IngestionStage))).scalars().all())
        totals: dict[StageName, StageCost] = {}
        for row in rows:
            entry = totals.setdefault(row.stage, StageCost(stage=row.stage.value))
            entry.input_tokens += row.input_tokens or 0
            entry.output_tokens += row.output_tokens or 0
            entry.cost_usd += row.cost_usd or 0.0
            entry.duration_ms += row.duration_ms or 0
        stages = [totals[name] for name in StageName if name in totals]

    return MetricsOut(
        book_id=book_id,
        stages=stages,
        total_cost_usd=sum(stage.cost_usd for stage in stages),
        prefix_cache_hit_rate=await _prefix_cache_hit_rate(),
    )


async def _prefix_cache_hit_rate() -> float | None:
    """Best-effort, live from vLLM -- never blocks or fails `/ops/metrics`.

    Only meaningful with a real local vLLM in front of pass 2 (S3.15,
    llm-runtime.md "Prefix caching is the cost argument"); `INFERENCE_MODE=api`
    has no prefix cache to report on, so this is skipped rather than scraping
    a URL that was never meant to serve one.

    This is vLLM's lifetime-cumulative rate since its last boot, not scoped
    to any one book or stage -- a live "what is the cache doing right now"
    reading, not a per-book measurement (S4.15 finding, plans/sprint-4/
    HANDOFF.md; a real per-book number needs a before/after delta, as
    `scripts/ingest_book.py` takes).
    """
    if settings.inference_mode != InferenceMode.LOCAL:
        return None

    stats = await fetch_vllm_cache_stats(settings.vllm_base_url)

    return stats.prefix_cache_hit_rate if stats else None

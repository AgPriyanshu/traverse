"""Pipeline health: run history, failure rates, dead-letter, retries, traces
(S9.3, F7.4) -- "what broke and where" on one screen, no terminal required.

Builds on ``api/ops/pipeline_status.py`` (``list_runs``, ``list_dead_letters``,
S2.17/S2.18), which already reads ``IngestionRun``/``IngestionStage`` and
already carries each run's ``trace_url``. This module adds the two things
that reading were missing: a failure rate per stage (across every run, not
just the latest) and a retry-outcome breakdown (did a retried stage
eventually succeed, or is it still stuck).
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import DeadLetterOut
from ..contracts.enums import StageState
from ..contracts.pipeline import IngestionRunOut
from ..db.models import IngestionRun, IngestionStage
from .pipeline_status import list_dead_letters, list_runs


class StageFailureRateOut(BaseModel):
    stage: str
    total: int
    failed: int
    failure_rate: float


class RetryOutcomeOut(BaseModel):
    """One stage's retried rows: did the last attempt land, or not.

    ``retried`` is any row with ``attempt > 0`` -- the stage's own
    upsert-in-place convention (`api/ops/pipeline_status.py`'s docstring)
    means ``attempt`` is already the retry count, not a separate counter.
    """

    stage: str
    retried: int
    eventually_succeeded: int
    still_failed: int


class PipelineHealthOut(BaseModel):
    """``GET /ops/pipeline-health`` response -- S9.3."""

    book_id: UUID | None
    runs: list[IngestionRunOut]
    failure_rates: list[StageFailureRateOut]
    retry_outcomes: list[RetryOutcomeOut]
    dead_letters: list[DeadLetterOut]


async def compute_failure_rates(
    session: SQLModelAsyncSession, *, book_id: UUID | None = None
) -> list[StageFailureRateOut]:
    """Failed / total for each stage, across every run that has ever reached it.

    Every row counts once towards ``total`` regardless of attempt number --
    this answers "how often does this stage fail on the way to done", not
    "how many individual attempts failed", which retry_outcomes covers.
    """
    statement = select(IngestionStage.stage, IngestionStage.state)
    if book_id is not None:
        statement = statement.join(
            IngestionRun, IngestionStage.run_id == IngestionRun.id  # type: ignore[arg-type]
        ).where(IngestionRun.book_id == book_id)  # type: ignore[arg-type]

    rows = (await session.execute(statement)).all()

    totals: dict[str, int] = {}
    failed: dict[str, int] = {}
    for stage, state in rows:
        key = stage.value
        totals[key] = totals.get(key, 0) + 1
        if state == StageState.FAILED:
            failed[key] = failed.get(key, 0) + 1

    return [
        StageFailureRateOut(
            stage=stage,
            total=total,
            failed=failed.get(stage, 0),
            failure_rate=(failed.get(stage, 0) / total) if total else 0.0,
        )
        for stage, total in sorted(totals.items())
    ]


async def compute_retry_outcomes(
    session: SQLModelAsyncSession, *, book_id: UUID | None = None
) -> list[RetryOutcomeOut]:
    """For every stage row that was retried at least once, how it ended up."""
    statement = select(IngestionStage.stage, IngestionStage.attempt, IngestionStage.state)
    statement = statement.where(IngestionStage.attempt > 0)  # type: ignore[operator]
    if book_id is not None:
        statement = statement.join(
            IngestionRun, IngestionStage.run_id == IngestionRun.id  # type: ignore[arg-type]
        ).where(IngestionRun.book_id == book_id)  # type: ignore[arg-type]

    rows = (await session.execute(statement)).all()

    retried: dict[str, int] = {}
    succeeded: dict[str, int] = {}
    still_failed: dict[str, int] = {}
    for stage, _attempt, state in rows:
        key = stage.value
        retried[key] = retried.get(key, 0) + 1
        if state == StageState.SUCCEEDED:
            succeeded[key] = succeeded.get(key, 0) + 1
        elif state == StageState.FAILED:
            still_failed[key] = still_failed.get(key, 0) + 1

    return [
        RetryOutcomeOut(
            stage=stage,
            retried=count,
            eventually_succeeded=succeeded.get(stage, 0),
            still_failed=still_failed.get(stage, 0),
        )
        for stage, count in sorted(retried.items())
    ]


async def compute_pipeline_health(
    session: SQLModelAsyncSession,
    *,
    book_id: UUID | None = None,
    limit: int = 50,
) -> PipelineHealthOut:
    runs = await list_runs(session, book_id=book_id, limit=limit)
    failure_rates = await compute_failure_rates(session, book_id=book_id)
    retry_outcomes = await compute_retry_outcomes(session, book_id=book_id)
    dead_letters = await list_dead_letters(session)
    if book_id is not None:
        dead_letters = [row for row in dead_letters if row.book_id == book_id]

    return PipelineHealthOut(
        book_id=book_id,
        runs=runs,
        failure_rates=failure_rates,
        retry_outcomes=retry_outcomes,
        dead_letters=dead_letters,
    )

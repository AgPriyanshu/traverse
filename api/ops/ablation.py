"""Persist and read ablation runs (S8.8, F6.3).

``scripts/run_ablation.py`` computes each cell's metrics against the live
``/ops/*-quality`` endpoints and calls :func:`record_eval_run` once per run to
write the frozen ``EvalRun``/``EvalResult`` tables (migration ``0011``). This
module is the only thing that reads them back, behind
``GET /ops/eval-runs/latest`` -- the read side fe1's S8.7 table consumes.

Kept thin on purpose: the matrix shape and metric mapping live in
``eval/ablation.py`` (pure, no Postgres), matching every other eval harness's
split between "the ``eval/`` scoring logic" and "the do1-owned DB adapter"
(see ``api/ops/extraction_quality.py``).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import AblationConfig, EvalResultOut, EvalRunOut, MetricSet
from ..db.models import EvalResult, EvalRun


async def record_eval_run(
    session: SQLModelAsyncSession,
    *,
    corpus_version: str | None,
    git_sha: str | None,
    notes: str | None,
    cells: list[dict[str, Any]],
) -> EvalRun:
    """Write one run and its cells in a single transaction.

    Args:
        cells: One dict per measured or blocked cell:
            ``axis``, ``label``, ``book_key``, ``config`` (an ``AblationConfig``
            -shaped dict) and ``metrics`` (a ``MetricSet``-shaped dict, all
            fields ``None``/``0`` for a blocked cell -- the run's own
            ``notes`` and each result's ``config`` are what record *why*).
    """
    measured_sample = sum(c["metrics"].get("sample_size") or 0 for c in cells)
    run = EvalRun(
        corpus_version=corpus_version,
        git_sha=git_sha,
        notes=notes,
        metrics=MetricSet(sample_size=measured_sample).model_dump(mode="json"),
    )
    session.add(run)
    await session.flush()

    for cell in cells:
        session.add(
            EvalResult(
                eval_run_id=run.id,
                axis=cell["axis"],
                label=cell["label"],
                book_key=cell.get("book_key"),
                config=cell["config"],
                metrics=cell["metrics"],
            )
        )

    await session.commit()
    await session.refresh(run)

    return run


def _to_out(run: EvalRun, results: list[EvalResult]) -> EvalRunOut:
    return EvalRunOut(
        id=run.id,
        corpus_version=run.corpus_version,
        git_sha=run.git_sha,
        metrics=MetricSet.model_validate(run.metrics),
        notes=run.notes,
        created_at=run.created_at,
        results=[
            EvalResultOut(
                id=r.id,
                eval_run_id=r.eval_run_id,
                axis=r.axis,
                label=r.label,
                book_key=r.book_key,
                config=AblationConfig.model_validate(r.config),
                metrics=MetricSet.model_validate(r.metrics),
            )
            for r in results
        ],
    )


async def get_latest_eval_run(session: SQLModelAsyncSession) -> EvalRunOut | None:
    """The most recently written run, with its results eager-loaded."""
    statement = (
        select(EvalRun)
        .options(selectinload(EvalRun.results))
        .order_by(EvalRun.created_at.desc())
        .limit(1)
    )
    result = await session.execute(statement)
    run = result.scalars().first()
    if run is None:
        return None

    return _to_out(run, run.results)


async def get_eval_run(session: SQLModelAsyncSession, run_id: UUID) -> EvalRunOut | None:
    statement = (
        select(EvalRun).options(selectinload(EvalRun.results)).where(EvalRun.id == run_id)
    )
    result = await session.execute(statement)
    run = result.scalars().first()
    if run is None:
        return None

    return _to_out(run, run.results)

"""Stage status recording — what ``GET /books/{id}/status`` reads."""

import time
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.enums import StageName, StageState
from ..db.engine import db_session
from ..db.models import IngestionRun, IngestionStage
from ..db.models.base import utcnow

# Truncated so one pathological traceback cannot bloat a status response.
MAX_TRACEBACK_CHARS = 8000


@dataclass
class StageRecord:
    """The handle a stage body uses to report what it did."""

    run_id: UUID
    stage_id: UUID
    stage: StageName
    attempt: int
    rows_written: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    _extras: dict[str, object] = field(default_factory=dict, repr=False)


async def open_run(session: SQLModelAsyncSession, book_id: UUID) -> IngestionRun:
    """Return the book's open ingestion run, creating one if none is open.

    A run stays open until every stage has finished, so a retry lands on the
    same run rather than fragmenting one book's history across several.

    Args:
        session: Session to use; the caller commits.
        book_id: Book being ingested.

    Returns:
        The open run.
    """
    statement = (
        select(IngestionRun)
        .where(IngestionRun.book_id == book_id)
        .where(IngestionRun.finished_at.is_(None))  # type: ignore[union-attr]
        .order_by(IngestionRun.created_at.desc())  # type: ignore[union-attr]
        .limit(1)
    )
    existing = (await session.execute(statement)).scalars().first()

    if existing is not None:
        return existing

    run = IngestionRun(book_id=book_id, started_at=utcnow())
    session.add(run)
    await session.flush()

    return run


async def finish_run(
    session: SQLModelAsyncSession, run_id: UUID, *, at: datetime | None = None
) -> None:
    """Close a run so the next ingestion of the same book starts a fresh one."""
    run = await session.get(IngestionRun, run_id)

    if run is not None:
        run.finished_at = at or utcnow()
        session.add(run)


async def _begin(book_id: UUID, stage_name: StageName) -> StageRecord:
    async with db_session() as session:
        run = await open_run(session, book_id)

        table = IngestionStage.__table__
        statement = (
            insert(table)
            .values(
                run_id=run.id,
                stage=stage_name,
                state=StageState.RUNNING,
                attempt=1,
                started_at=utcnow(),
            )
            .on_conflict_do_update(
                constraint="uq_stage_run_stage",
                set_={
                    "state": StageState.RUNNING,
                    "attempt": table.c.attempt + 1,
                    "started_at": utcnow(),
                    "finished_at": None,
                    "duration_ms": None,
                    "error_class": None,
                    "error_message": None,
                    "traceback": None,
                    "updated_at": utcnow(),
                },
            )
            .returning(table.c.id, table.c.attempt)
        )
        stage_id, attempt = (await session.execute(statement)).one()
        await session.commit()

        return StageRecord(
            run_id=run.id, stage_id=stage_id, stage=stage_name, attempt=attempt
        )


async def _settle(
    record: StageRecord, state: StageState, started: float, exc: BaseException | None
) -> None:
    values: dict[str, object] = {
        "state": state,
        "finished_at": utcnow(),
        "duration_ms": int((time.monotonic() - started) * 1000),
        "rows_written": record.rows_written,
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "cost_usd": record.cost_usd,
        "updated_at": utcnow(),
    }

    if exc is not None:
        formatted = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
        values["error_class"] = type(exc).__name__
        values["error_message"] = str(exc)[:1000]
        values["traceback"] = formatted[-MAX_TRACEBACK_CHARS:]

    async with db_session() as session:
        await session.execute(
            IngestionStage.__table__.update()
            .where(IngestionStage.__table__.c.id == record.stage_id)
            .values(**values)
        )
        await session.commit()


@asynccontextmanager
async def stage(book_id: UUID, stage_name: StageName) -> AsyncIterator[StageRecord]:
    """Record one stage attempt, whatever happens inside it.

    The row is written in its own transaction, separate from the stage's work.
    A stage that rolls back its data must still leave a readable failure
    behind, otherwise a crashed book looks identical to one that was never
    started.

    A process killed mid-stage leaves the row ``running`` with no
    ``finished_at`` — that is the signal a retry is owed, and re-entering this
    manager bumps ``attempt`` rather than orphaning the row.

    Args:
        book_id: Book being ingested.
        stage_name: The frozen stage/task name.

    Yields:
        A ``StageRecord`` whose counters the body may set before returning.

    Example:
        >>> async with stage(book_id, StageName.EMBED_CHUNKS) as s:
        ...     s.rows_written = await embed(book_id)
    """
    record = await _begin(book_id, stage_name)
    started = time.monotonic()

    try:
        yield record
    except BaseException as exc:
        await _settle(record, StageState.FAILED, started, exc)
        raise

    await _settle(record, StageState.SUCCEEDED, started, None)

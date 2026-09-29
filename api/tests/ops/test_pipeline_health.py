from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import StageName, StageState
from api.db.models import Book, IngestionRun, IngestionStage, Project
from api.ops.pipeline_health import (
    compute_failure_rates,
    compute_pipeline_health,
    compute_retry_outcomes,
)


async def _run_with_stage(
    session: SQLModelAsyncSession,
    book: Book,
    *,
    stage: StageName,
    state: StageState,
    attempt: int = 0,
    trace_url: str | None = None,
) -> IngestionRun:
    run = IngestionRun(book_id=book.id, trace_url=trace_url)
    session.add(run)
    await session.commit()
    await session.refresh(run)

    session.add(
        IngestionStage(run_id=run.id, stage=stage, state=state, attempt=attempt)
    )
    await session.commit()
    return run


async def test_failure_rate_counts_failed_over_total(
    session: SQLModelAsyncSession, project: Project, book: Book
) -> None:
    await _run_with_stage(
        session, book, stage=StageName.EXTRACT_RELATIONS, state=StageState.SUCCEEDED
    )
    await _run_with_stage(
        session, book, stage=StageName.EXTRACT_RELATIONS, state=StageState.FAILED
    )
    await _run_with_stage(
        session, book, stage=StageName.EXTRACT_RELATIONS, state=StageState.FAILED
    )

    rates = await compute_failure_rates(session, book_id=book.id)
    row = next(r for r in rates if r.stage == StageName.EXTRACT_RELATIONS.value)

    assert row.total == 3
    assert row.failed == 2
    assert row.failure_rate == 2 / 3


async def test_retry_outcomes_split_succeeded_vs_still_failed(
    session: SQLModelAsyncSession, project: Project, book: Book
) -> None:
    await _run_with_stage(
        session,
        book,
        stage=StageName.EMBED_CHUNKS,
        state=StageState.SUCCEEDED,
        attempt=1,
    )
    await _run_with_stage(
        session,
        book,
        stage=StageName.EMBED_CHUNKS,
        state=StageState.FAILED,
        attempt=2,
    )
    # Not a retry — attempt 0 must not count towards either bucket.
    await _run_with_stage(
        session,
        book,
        stage=StageName.EMBED_CHUNKS,
        state=StageState.SUCCEEDED,
        attempt=0,
    )

    outcomes = await compute_retry_outcomes(session, book_id=book.id)
    row = next(o for o in outcomes if o.stage == StageName.EMBED_CHUNKS.value)

    assert row.retried == 2
    assert row.eventually_succeeded == 1
    assert row.still_failed == 1


async def test_pipeline_health_includes_trace_link_and_dead_letter(
    session: SQLModelAsyncSession, project: Project, book: Book
) -> None:
    await _run_with_stage(
        session,
        book,
        stage=StageName.EXTRACT_RELATIONS,
        state=StageState.FAILED,
        trace_url="https://langfuse.local/trace/abc123",
    )

    out = await compute_pipeline_health(session, book_id=book.id)

    assert len(out.runs) == 1
    assert out.runs[0].trace_url == "https://langfuse.local/trace/abc123"
    assert len(out.dead_letters) == 1
    assert out.dead_letters[0].book_id == book.id


async def test_pipeline_health_empty_for_book_with_no_runs(
    session: SQLModelAsyncSession, project: Project, book: Book
) -> None:
    out = await compute_pipeline_health(session, book_id=book.id)

    assert out.runs == []
    assert out.failure_rates == []
    assert out.retry_outcomes == []
    assert out.dead_letters == []

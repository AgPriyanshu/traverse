from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import StageName, StageState
from api.db.models import Book, IngestionRun, IngestionStage, Project
from api.ops.performance_telemetry import _queue_depth, compute_performance


async def _run_with_stage(
    session: SQLModelAsyncSession,
    book: Book,
    *,
    stage: StageName,
    duration_ms: int,
) -> None:
    run = IngestionRun(book_id=book.id)
    session.add(run)
    await session.commit()
    await session.refresh(run)

    session.add(
        IngestionStage(
            run_id=run.id,
            stage=stage,
            state=StageState.SUCCEEDED,
            duration_ms=duration_ms,
        )
    )
    await session.commit()


async def test_stage_latency_percentiles_grouped_by_stage(
    session: SQLModelAsyncSession, project: Project, book: Book
) -> None:
    for ms in (100, 200, 300, 400, 500):
        await _run_with_stage(
            session, book, stage=StageName.EXTRACT_CHARACTERS, duration_ms=ms
        )

    out = await compute_performance(session, book_id=None)

    stage_key = StageName.EXTRACT_CHARACTERS.value
    assert stage_key in out.stage_latency_ms
    pct = out.stage_latency_ms[stage_key]
    assert pct.n == 5
    assert pct.p50 == 300


async def test_ingestion_throughput_uses_parse_stage_and_page_count(
    session: SQLModelAsyncSession, project: Project, book: Book
) -> None:
    # book fixture has page_count=3; 60_000ms for 3 pages == 100ms/page ==
    # 3 pages / (60_000ms / 60_000) == 3 pages/min at this rate... compute
    # directly instead of restating the formula: 3 pages in 60s == 3/min.
    await _run_with_stage(
        session, book, stage=StageName.PARSE_AND_CHUNK, duration_ms=60_000
    )

    out = await compute_performance(session, book_id=book.id)

    assert len(out.ingestion_throughput) == 1
    entry = out.ingestion_throughput[0]
    assert entry.book_id == book.id
    assert entry.pages_per_minute == 3.0


async def test_performance_has_no_data_without_any_runs(
    session: SQLModelAsyncSession,
) -> None:
    out = await compute_performance(session, book_id=None)

    assert out.stage_latency_ms == {}
    assert out.ingestion_throughput == []


def test_queue_depth_never_raises() -> None:
    # A shared-singleton broker (BRANCH.md §9) may or may not have a worker
    # registered when this runs, and any of the three inspect calls can come
    # back empty independently -- the one thing this asserts is that it never
    # raises and every field is either `None` or a non-negative count.
    out = _queue_depth()
    for value in (out.active, out.reserved, out.scheduled):
        assert value is None or value >= 0

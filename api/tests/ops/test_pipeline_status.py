import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import StageName, StageState
from api.db.models import Book, IngestionRun, IngestionStage
from api.db.models.project_model import Project
from api.ops import pipeline_status


async def _make_run(
    session: SQLModelAsyncSession,
    book: Book,
    *,
    created_at: datetime,
    trace_url: str | None = None,
) -> IngestionRun:
    run = IngestionRun(book_id=book.id, trace_url=trace_url)
    session.add(run)
    await session.commit()
    await session.refresh(run)

    # created_at is server/default-assigned by TimestampMixin; force the value
    # under test so "latest run" ordering is deterministic instead of racing
    # on wall-clock resolution between rows created in the same test.
    run.created_at = created_at
    session.add(run)
    await session.commit()
    await session.refresh(run)

    return run


async def _make_stage(
    session: SQLModelAsyncSession,
    run: IngestionRun,
    stage: StageName,
    *,
    state: StageState = StageState.SUCCEEDED,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cost_usd: float | None = None,
    duration_ms: int | None = None,
    error_class: str | None = None,
    error_message: str | None = None,
) -> IngestionStage:
    row = IngestionStage(
        run_id=run.id,
        stage=stage,
        state=state,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        duration_ms=duration_ms,
        error_class=error_class,
        error_message=error_message,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return row


async def test_list_runs_orders_stages_by_pipeline_not_insert_order(
    session: SQLModelAsyncSession, book: Book
) -> None:
    run = await _make_run(
        session, book, created_at=datetime.now(UTC), trace_url="https://langfuse/t/1"
    )
    # Insert out of pipeline order on purpose.
    await _make_stage(session, run, StageName.EMBED_CHUNKS)
    await _make_stage(session, run, StageName.PARSE_AND_CHUNK)
    await _make_stage(session, run, StageName.SEGMENT_CHAPTERS)

    [out] = await pipeline_status.list_runs(session, book_id=book.id)

    assert out.run_id == run.id
    assert out.trace_url == "https://langfuse/t/1"
    assert [s.stage for s in out.stages] == [
        StageName.PARSE_AND_CHUNK,
        StageName.SEGMENT_CHAPTERS,
        StageName.EMBED_CHUNKS,
    ]


async def test_list_runs_newest_first_and_book_filter(
    session: SQLModelAsyncSession, project: Project, book: Book
) -> None:
    other_book = Book(
        project_id=project.id,
        title="Another Novel",
        author="B. Author",
        content_hash=uuid.uuid4().hex,
        page_count=1,
    )
    session.add(other_book)
    await session.commit()
    await session.refresh(other_book)

    now = datetime.now(UTC)
    older = await _make_run(session, book, created_at=now - timedelta(minutes=5))
    newer = await _make_run(session, book, created_at=now)
    await _make_run(session, other_book, created_at=now)

    runs = await pipeline_status.list_runs(session, book_id=book.id)

    assert [r.run_id for r in runs] == [newer.id, older.id]


async def test_list_runs_respects_limit(
    session: SQLModelAsyncSession, book: Book
) -> None:
    now = datetime.now(UTC)
    for i in range(3):
        await _make_run(session, book, created_at=now - timedelta(minutes=i))

    runs = await pipeline_status.list_runs(session, book_id=book.id, limit=2)

    assert len(runs) == 2


async def test_list_runs_empty_when_no_runs(
    session: SQLModelAsyncSession, book: Book
) -> None:
    assert await pipeline_status.list_runs(session, book_id=book.id) == []


async def test_dead_letter_lists_book_with_failed_stage_on_latest_run(
    session: SQLModelAsyncSession, book: Book
) -> None:
    run = await _make_run(
        session, book, created_at=datetime.now(UTC), trace_url="https://langfuse/t/2"
    )
    await _make_stage(
        session,
        run,
        StageName.EXTRACT_CHARACTERS,
        state=StageState.FAILED,
        error_class="ValueError",
        error_message="boom",
    )

    [entry] = await pipeline_status.list_dead_letters(session)

    assert entry.book_id == book.id
    assert entry.book_title == book.title
    assert entry.stage == StageName.EXTRACT_CHARACTERS.value
    assert entry.error_class == "ValueError"
    assert entry.trace_url == "https://langfuse/t/2"


async def test_dead_letter_ignores_failure_on_a_superseded_run(
    session: SQLModelAsyncSession, book: Book
) -> None:
    now = datetime.now(UTC)
    failed_run = await _make_run(session, book, created_at=now - timedelta(minutes=5))
    await _make_stage(
        session, failed_run, StageName.EXTRACT_CHARACTERS, state=StageState.FAILED
    )

    retried_run = await _make_run(session, book, created_at=now)
    await _make_stage(
        session, retried_run, StageName.EXTRACT_CHARACTERS, state=StageState.SUCCEEDED
    )

    assert await pipeline_status.list_dead_letters(session) == []


async def test_get_metrics_for_a_book_reads_its_latest_run(
    session: SQLModelAsyncSession, book: Book
) -> None:
    now = datetime.now(UTC)
    older_run = await _make_run(session, book, created_at=now - timedelta(minutes=5))
    await _make_stage(
        session,
        older_run,
        StageName.PARSE_AND_CHUNK,
        input_tokens=999,
        output_tokens=999,
        cost_usd=99.0,
        duration_ms=999,
    )

    latest_run = await _make_run(session, book, created_at=now)
    await _make_stage(
        session,
        latest_run,
        StageName.PARSE_AND_CHUNK,
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
        duration_ms=1200,
    )

    metrics = await pipeline_status.get_metrics(session, book_id=book.id)

    assert metrics.book_id == book.id
    assert len(metrics.stages) == 1
    stage = metrics.stages[0]
    assert stage.stage == StageName.PARSE_AND_CHUNK.value
    assert stage.input_tokens == 100
    assert stage.output_tokens == 50
    assert stage.cost_usd == pytest.approx(0.01)
    assert metrics.total_cost_usd == pytest.approx(0.01)


async def test_get_metrics_for_unknown_book_is_empty(
    session: SQLModelAsyncSession,
) -> None:
    metrics = await pipeline_status.get_metrics(session, book_id=uuid.uuid4())

    assert metrics.stages == []
    assert metrics.total_cost_usd == 0.0


async def test_get_metrics_without_book_id_sums_every_run(
    session: SQLModelAsyncSession, project: Project
) -> None:
    book_a = Book(
        project_id=project.id,
        title="Book A",
        author="A",
        content_hash=uuid.uuid4().hex,
        page_count=1,
    )
    book_b = Book(
        project_id=project.id,
        title="Book B",
        author="B",
        content_hash=uuid.uuid4().hex,
        page_count=1,
    )
    session.add(book_a)
    session.add(book_b)
    await session.commit()
    await session.refresh(book_a)
    await session.refresh(book_b)

    run_a = await _make_run(session, book_a, created_at=datetime.now(UTC))
    run_b = await _make_run(session, book_b, created_at=datetime.now(UTC))
    await _make_stage(
        session,
        run_a,
        StageName.EMBED_CHUNKS,
        input_tokens=10,
        output_tokens=0,
        cost_usd=0.001,
        duration_ms=500,
    )
    await _make_stage(
        session,
        run_b,
        StageName.EMBED_CHUNKS,
        input_tokens=20,
        output_tokens=0,
        cost_usd=0.002,
        duration_ms=700,
    )

    metrics = await pipeline_status.get_metrics(session)

    assert metrics.book_id is None
    [stage] = metrics.stages
    assert stage.stage == StageName.EMBED_CHUNKS.value
    assert stage.input_tokens == 30
    assert stage.duration_ms == 1200
    assert metrics.total_cost_usd == pytest.approx(0.003)

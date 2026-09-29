from datetime import UTC, datetime, timedelta

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import LLMPurpose, QueryRoute, StageName, StageState
from api.db.models import Book, IngestionRun, IngestionStage, Project, QueryLog
from api.ops.cost_telemetry import (
    compute_cost_breakdown,
    cost_per_book,
    cost_per_query,
    list_cost_snapshots,
    rolling_window,
    save_cost_snapshot,
)


async def _run_with_stage(
    session: SQLModelAsyncSession,
    book: Book,
    *,
    stage: StageName,
    cost_usd: float,
    created_at: datetime | None = None,
) -> None:
    run = IngestionRun(book_id=book.id)
    session.add(run)
    await session.commit()
    await session.refresh(run)

    stage_row = IngestionStage(
        run_id=run.id,
        stage=stage,
        state=StageState.SUCCEEDED,
        cost_usd=cost_usd,
        input_tokens=1000,
        output_tokens=200,
    )
    session.add(stage_row)
    await session.commit()
    if created_at is not None:
        stage_row.created_at = created_at
        session.add(stage_row)
        await session.commit()


async def test_rolling_window_is_now_minus_days() -> None:
    start, end = rolling_window(days=1)
    assert (end - start) == timedelta(days=1)
    assert end <= datetime.now(UTC) + timedelta(seconds=5)


async def test_cost_breakdown_groups_by_stage_and_purpose(
    session: SQLModelAsyncSession, project: Project, book: Book
) -> None:
    await _run_with_stage(
        session, book, stage=StageName.EXTRACT_CHARACTERS, cost_usd=1.5
    )
    await _run_with_stage(
        session, book, stage=StageName.EXTRACT_RELATIONS, cost_usd=3.0
    )

    window_start, window_end = rolling_window(days=1)
    breakdown = await compute_cost_breakdown(
        session, window_start=window_start, window_end=window_end
    )

    assert breakdown.by_stage[StageName.EXTRACT_CHARACTERS.value] == 1.5
    assert breakdown.by_stage[StageName.EXTRACT_RELATIONS.value] == 3.0
    assert breakdown.by_purpose[LLMPurpose.CHARACTER_EXTRACT.value] == 1.5
    assert breakdown.by_purpose[LLMPurpose.RELATION_EXTRACT.value] == 3.0
    assert breakdown.total_cost_usd == 4.5
    assert breakdown.book_count == 1


async def test_cost_breakdown_excludes_rows_outside_the_window(
    session: SQLModelAsyncSession, project: Project, book: Book
) -> None:
    old = datetime.now(UTC) - timedelta(days=10)
    await _run_with_stage(
        session, book, stage=StageName.EXTRACT_CHARACTERS, cost_usd=9.0, created_at=old
    )

    window_start, window_end = rolling_window(days=1)
    breakdown = await compute_cost_breakdown(
        session, window_start=window_start, window_end=window_end
    )

    assert breakdown.total_cost_usd == 0.0
    assert breakdown.book_count == 0


async def test_query_cost_rolls_into_answer_purpose(
    session: SQLModelAsyncSession, project: Project
) -> None:
    session.add(
        QueryLog(
            project_id=project.id,
            question="who is Elizabeth?",
            route=QueryRoute.CHARACTER_LOOKUP,
            cost_usd=0.02,
        )
    )
    await session.commit()

    window_start, window_end = rolling_window(days=1)
    breakdown = await compute_cost_breakdown(
        session, window_start=window_start, window_end=window_end
    )

    assert breakdown.query_count == 1
    assert breakdown.by_purpose[LLMPurpose.ANSWER.value] == 0.02
    assert breakdown.total_cost_usd == 0.02


async def test_cost_per_book_and_per_query_ratios(
    session: SQLModelAsyncSession, project: Project, book: Book
) -> None:
    await _run_with_stage(
        session, book, stage=StageName.EXTRACT_CHARACTERS, cost_usd=2.0
    )
    session.add(
        QueryLog(
            project_id=project.id,
            question="who is Darcy?",
            cost_usd=0.10,
        )
    )
    await session.commit()

    window_start, window_end = rolling_window(days=1)
    breakdown = await compute_cost_breakdown(
        session, window_start=window_start, window_end=window_end
    )

    assert cost_per_book(breakdown) == 2.0
    assert cost_per_query(breakdown) == 0.10


async def test_cost_per_book_and_query_are_none_without_data(
    session: SQLModelAsyncSession,
) -> None:
    window_start, window_end = rolling_window(days=1)
    breakdown = await compute_cost_breakdown(
        session, window_start=window_start, window_end=window_end
    )

    assert cost_per_book(breakdown) is None
    assert cost_per_query(breakdown) is None


async def test_save_and_list_cost_snapshots(
    session: SQLModelAsyncSession, project: Project, book: Book
) -> None:
    await _run_with_stage(
        session, book, stage=StageName.EXTRACT_CHARACTERS, cost_usd=1.0
    )

    window_start, window_end = rolling_window(days=1)
    breakdown = await compute_cost_breakdown(
        session, window_start=window_start, window_end=window_end
    )
    saved = await save_cost_snapshot(session, breakdown)
    assert saved.id is not None

    rows = await list_cost_snapshots(session, limit=10)
    assert len(rows) == 1
    assert rows[0].total_cost_usd == 1.0

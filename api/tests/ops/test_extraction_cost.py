from datetime import UTC, datetime

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import StageName, StageState
from api.db.models import Book, IngestionRun, IngestionStage
from api.ops.extraction_cost import compute_extraction_cost


async def _run_with_extraction_stages(
    session: SQLModelAsyncSession, book: Book
) -> IngestionRun:
    run = IngestionRun(book_id=book.id)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    run.created_at = datetime.now(UTC)
    session.add(run)
    await session.commit()

    session.add(
        IngestionStage(
            run_id=run.id,
            stage=StageName.EXTRACT_CHARACTERS,
            state=StageState.SUCCEEDED,
            input_tokens=200_000,
            output_tokens=20_000,
            cost_usd=0.05,
            duration_ms=120_000,
        )
    )
    session.add(
        IngestionStage(
            run_id=run.id,
            stage=StageName.RESOLVE_ALIASES,
            state=StageState.SUCCEEDED,
            input_tokens=50_000,
            output_tokens=5_000,
            cost_usd=0.01,
            duration_ms=30_000,
        )
    )
    # A non-extraction stage must not leak into this report.
    session.add(
        IngestionStage(
            run_id=run.id,
            stage=StageName.EMBED_CHUNKS,
            state=StageState.SUCCEEDED,
            input_tokens=1,
            output_tokens=0,
            cost_usd=0.0001,
            duration_ms=1000,
        )
    )
    await session.commit()

    return run


async def test_extraction_cost_reports_both_llm_heavy_stages_only(
    session: SQLModelAsyncSession, book: Book
) -> None:
    # `book` fixture is 3 pages (api/tests/conftest.py) -- override for a
    # realistic per-100-pages figure.
    book.page_count = 300
    session.add(book)
    await session.commit()

    await _run_with_extraction_stages(session, book)

    result = await compute_extraction_cost(session, book.id)

    assert {s.stage for s in result.stages} == {
        StageName.EXTRACT_CHARACTERS.value,
        StageName.RESOLVE_ALIASES.value,
    }
    extract = next(
        s for s in result.stages if s.stage == StageName.EXTRACT_CHARACTERS.value
    )
    assert extract.input_tokens == 200_000
    assert extract.duration_ms == 120_000
    # 300 pages -> 3x the "per 100 pages" unit, so normalised time is 1/3 raw.
    assert extract.wall_clock_ms_per_100_pages == pytest.approx(40_000)
    assert result.total_cost_usd_local == pytest.approx(0.06)


async def test_extraction_cost_for_a_book_with_no_run_yet_is_empty(
    session: SQLModelAsyncSession, book: Book
) -> None:
    result = await compute_extraction_cost(session, book.id)

    assert result.stages == []
    assert result.total_cost_usd_local == 0.0
    assert result.total_cost_usd_api_equivalent is None

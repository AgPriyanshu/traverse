from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import StageName, StageState
from api.db.models import Book, IngestionRun, IngestionStage, Project
from api.ops.budget_guard import (
    DEFAULT_MONTHLY_BUDGET_USD,
    compute_budget_status,
    monthly_budget_usd,
)


def test_monthly_budget_defaults_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("MONTHLY_BUDGET_USD", raising=False)
    assert monthly_budget_usd() == DEFAULT_MONTHLY_BUDGET_USD


def test_monthly_budget_reads_env_override(monkeypatch) -> None:
    monkeypatch.setenv("MONTHLY_BUDGET_USD", "12.5")
    assert monthly_budget_usd() == 12.5


def test_monthly_budget_falls_back_on_garbage(monkeypatch) -> None:
    monkeypatch.setenv("MONTHLY_BUDGET_USD", "not-a-number")
    assert monthly_budget_usd() == DEFAULT_MONTHLY_BUDGET_USD


async def test_budget_status_breaches_over_the_cap(
    session: SQLModelAsyncSession, project: Project, book: Book, monkeypatch
) -> None:
    monkeypatch.setenv("MONTHLY_BUDGET_USD", "1.0")

    run = IngestionRun(book_id=book.id)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    session.add(
        IngestionStage(
            run_id=run.id,
            stage=StageName.EXTRACT_RELATIONS,
            state=StageState.SUCCEEDED,
            cost_usd=5.0,
        )
    )
    await session.commit()

    status = await compute_budget_status(session)

    assert status.spent_usd == 5.0
    assert status.breached is True
    assert status.warning is True
    assert status.remaining_usd == 0.0


async def test_budget_status_under_cap_is_not_breached(
    session: SQLModelAsyncSession, monkeypatch
) -> None:
    monkeypatch.setenv("MONTHLY_BUDGET_USD", "100.0")

    status = await compute_budget_status(session)

    assert status.spent_usd == 0.0
    assert status.breached is False
    assert status.warning is False

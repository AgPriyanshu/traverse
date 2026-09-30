from __future__ import annotations

import os

from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from .cost_telemetry import compute_cost_breakdown, rolling_window

DEFAULT_MONTHLY_BUDGET_USD = 50.0
# Warn before the hard stop so an operator sees it coming on the dashboard,
# not just at the moment ingestion actually pauses.
WARNING_THRESHOLD = 0.8


def monthly_budget_usd() -> float:
    raw = os.environ.get("MONTHLY_BUDGET_USD")
    if not raw:
        return DEFAULT_MONTHLY_BUDGET_USD
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_MONTHLY_BUDGET_USD


class BudgetStatusOut(BaseModel):
    budget_usd: float
    spent_usd: float
    remaining_usd: float
    pct_used: float
    warning: bool
    breached: bool


async def compute_budget_status(session: SQLModelAsyncSession) -> BudgetStatusOut:
    budget = monthly_budget_usd()
    window_start, window_end = rolling_window(days=30)
    breakdown = await compute_cost_breakdown(
        session, window_start=window_start, window_end=window_end
    )
    spent = breakdown.total_cost_usd
    pct_used = (spent / budget) if budget > 0 else 1.0

    return BudgetStatusOut(
        budget_usd=budget,
        spent_usd=spent,
        remaining_usd=max(budget - spent, 0.0),
        pct_used=pct_used,
        warning=pct_used >= WARNING_THRESHOLD,
        breached=pct_used >= 1.0,
    )

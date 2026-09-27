"""Latency-budget metrics against PRD NFR-perf (S6.15).

Pure functions over plain data, so they are testable without Postgres or a
running API -- same shape as ``eval/relation_metrics.py``.
``api/ops/query_latency.py`` adapts real ``QueryLog`` rows into
``LatencySample`` values; everything here speaks plain numbers.

Budgets (PRD NFR-perf, devops-1.md S6.15): p95 end-to-end <= 6s, time to
first token <= 1.5s. Both are judged on the **integration host only**
(BRANCH.md §9) -- vLLM is a single-GPU host singleton shared by every
worktree, so a timing measured from a worktree is not a valid gate input and
must never be compared against these budgets.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from math import ceil, floor
from typing import Any

P95_BUDGET_MS = 6_000
TTFT_BUDGET_MS = 1_500


def percentile(values: list[float], p: float) -> float | None:
    """Linear-interpolated percentile, ``p`` in ``[0, 1]``. ``None`` if empty."""
    if not values:
        return None

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (len(ordered) - 1) * p
    lo, hi = floor(rank), ceil(rank)
    if lo == hi:
        return ordered[int(rank)]

    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


@dataclass(frozen=True)
class LatencySample:
    """One answered question's timing, adapted from ``QueryLog``.

    ``stages`` is whatever per-stage breakdown the query pipeline recorded in
    ``QueryLog.latency_ms`` (route/retrieve/generate — the exact key set is
    be2's to define; this module does not assume specific keys beyond
    ``total_ms``/``ttft_ms``, which are read explicitly rather than inferred).
    """

    total_ms: float
    ttft_ms: float | None = None
    cost_usd: float | None = None
    stages: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PercentileSet:
    p50: float | None
    p95: float | None
    p99: float | None
    n: int


def _percentiles(values: list[float]) -> PercentileSet:
    return PercentileSet(
        p50=percentile(values, 0.50),
        p95=percentile(values, 0.95),
        p99=percentile(values, 0.99),
        n=len(values),
    )


@dataclass
class LatencySummary:
    total: PercentileSet
    ttft: PercentileSet
    per_stage: dict[str, PercentileSet]
    avg_cost_usd: float | None
    sample_count: int
    p95_within_budget: bool | None
    ttft_p95_within_budget: bool | None


def summarize(samples: Iterable[LatencySample]) -> LatencySummary:
    """p50/p95/p99 for total latency, TTFT, and each named stage.

    Returns:
        Percentile sets plus the two NFR-perf gate booleans (``None`` when
        there are no samples to judge — an empty run is not a pass).
    """
    rows = list(samples)
    totals = [r.total_ms for r in rows]
    ttfts = [r.ttft_ms for r in rows if r.ttft_ms is not None]
    costs = [r.cost_usd for r in rows if r.cost_usd is not None]

    stage_values: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        for stage, ms in row.stages.items():
            stage_values[stage].append(ms)

    total_pct = _percentiles(totals)
    ttft_pct = _percentiles(ttfts)

    return LatencySummary(
        total=total_pct,
        ttft=ttft_pct,
        per_stage={stage: _percentiles(values) for stage, values in stage_values.items()},
        avg_cost_usd=(sum(costs) / len(costs)) if costs else None,
        sample_count=len(rows),
        p95_within_budget=(total_pct.p95 <= P95_BUDGET_MS) if total_pct.p95 is not None else None,
        ttft_p95_within_budget=(
            ttft_pct.p95 <= TTFT_BUDGET_MS if ttft_pct.p95 is not None else None
        ),
    )


def budget_violations(summary: LatencySummary) -> list[str]:
    """Human-readable breaches, empty when the budget holds (or is untested)."""
    problems = []
    if summary.sample_count == 0:
        return ["no samples — the gate cannot pass on zero questions"]

    if summary.p95_within_budget is False:
        problems.append(
            f"p95 latency {summary.total.p95:.0f}ms exceeds the {P95_BUDGET_MS}ms budget"
        )
    if summary.ttft_p95_within_budget is False:
        problems.append(
            f"p95 TTFT {summary.ttft.p95:.0f}ms exceeds the {TTFT_BUDGET_MS}ms budget"
        )

    return problems


def sample_from_query_log_row(row: dict[str, Any]) -> LatencySample | None:
    """Adapt one ``QueryLog`` row (as JSON) into a ``LatencySample``.

    ``latency_ms`` is a JSONB dict (``ops_model.py::QueryLog``); this reads
    ``total``/``ttft`` keys if present and otherwise sums every numeric entry
    as the total. Returns ``None`` for a row with no latency data at all
    (e.g. the pipeline errored before logging timing).
    """
    latency = row.get("latency_ms")
    if not latency:
        return None

    ttft = latency.get("ttft")
    total = latency.get("total")
    if total is None:
        numeric = [v for k, v in latency.items() if k != "ttft" and isinstance(v, (int, float))]
        total = sum(numeric) if numeric else None
    if total is None:
        return None

    stages = {
        k: v
        for k, v in latency.items()
        if k not in ("ttft", "total") and isinstance(v, (int, float))
    }

    return LatencySample(
        total_ms=float(total),
        ttft_ms=float(ttft) if ttft is not None else None,
        cost_usd=row.get("cost_usd"),
        stages=stages,
    )

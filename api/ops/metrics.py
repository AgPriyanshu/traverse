"""Cost accounting for LLM calls. Owned by devops engineer 1.

Per-stage timing, row counts, and DB persistence into ``ingestion_stage``
already exist in ``api/workers/stages.py`` (be1's ``stage()`` context
manager, S1). This module is scoped to the one piece that stayed unbuilt:
turning a token count into a dollar figure, so ``StageRecord.cost_usd`` (and
``QueryLog.cost_usd``, S6) are never a silent 0. `api/llm/budget.py` (S2.7,
be1/be2) calls ``estimate_cost_usd`` after each model call and sets the
result on the stage/query record it already owns.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCost:
    """USD per 1,000,000 tokens."""

    input_per_1m: float
    output_per_1m: float
    note: str = ""


# Local inference is not free — PRD NFR-cost calls out "local is free" as the
# wrong number. This amortises an on-demand GPU-hour into a $/1M-token rate at
# vLLM's measured throughput, so the local-vs-API comparison is an honest one.
# Both figures are placeholders pending a real integration-host measurement
# (BRANCH.md §9: timings from a worktree are invalid) — update alongside the
# nightly ingestion trend job (S2.18) once it has produced real numbers.
_LOCAL_GPU_USD_PER_HOUR = 1.10  # on-demand L40S-class instance, list price ballpark.
_LOCAL_TOKENS_PER_HOUR = 1_400_000  # placeholder; replace from real vLLM logs.
_LOCAL_USD_PER_1M = round(
    _LOCAL_GPU_USD_PER_HOUR / (_LOCAL_TOKENS_PER_HOUR / 1_000_000), 4
)

# Keyed by the exact model id `settings.llm_model` / a call's `model` field
# resolves to — not by "local"/"api" — so a lookup never has to guess which
# deployment served a given call.
COST_TABLE: dict[str, ModelCost] = {
    "Qwen/Qwen3-8B-AWQ": ModelCost(
        input_per_1m=_LOCAL_USD_PER_1M,
        output_per_1m=_LOCAL_USD_PER_1M,
        note="local vLLM, amortised GPU-hour — not a metered API rate",
    ),
    # api/llm/routing.py (S2.7) picks the routed model for INFERENCE_MODE=api;
    # add its entry here once that lands rather than guessing at one now.
}


def estimate_cost_usd(
    model: str, input_tokens: int, output_tokens: int
) -> float | None:
    """USD for one call, or ``None`` if ``model`` has no cost entry.

    ``None`` rather than ``0.0`` on purpose: a model missing from
    ``COST_TABLE`` must show up as a gap in the cost dashboard (F7.1), not
    read as a free call.
    """
    cost = COST_TABLE.get(model)
    if cost is None:
        return None
    return (
        input_tokens * cost.input_per_1m + output_tokens * cost.output_per_1m
    ) / 1_000_000


# S3.15: "USD at both local-amortised and API rates" -- a comparison figure,
# not a second real bill. Keyed by the same model id as COST_TABLE so a
# caller can look both up side by side for one call. Ballpark hosted-inference
# pricing for an 8B-class AWQ model as of this sprint; replace with a real
# quoted rate before this number appears anywhere a reader could mistake it
# for a committed price (same honesty bar as `_LOCAL_GPU_USD_PER_HOUR` above).
API_EQUIVALENT_COST_TABLE: dict[str, ModelCost] = {
    "Qwen/Qwen3-8B-AWQ": ModelCost(
        input_per_1m=0.06,
        output_per_1m=0.12,
        note="placeholder hosted-inference ballpark, not a quoted rate",
    ),
}


def estimate_api_equivalent_cost_usd(
    model: str, input_tokens: int, output_tokens: int
) -> float | None:
    """What the same call would cost at a hosted-API rate instead of local.

    The comparison `estimate_cost_usd` cannot make on its own: that function
    reports what was actually paid (local-amortised, if `model` served
    locally), never what the alternative would have cost.
    """
    cost = API_EQUIVALENT_COST_TABLE.get(model)
    if cost is None:
        return None
    return (
        input_tokens * cost.input_per_1m + output_tokens * cost.output_per_1m
    ) / 1_000_000


def wall_clock_ms_per_100_pages(
    duration_ms: int, page_count: int | None
) -> float | None:
    """Normalise a stage's wall clock so books of different lengths compare.

    Returns ``None`` rather than dividing by zero when `page_count` is
    missing or zero -- a book still mid-parse has no page count yet.
    """
    if not page_count:
        return None

    return duration_ms / (page_count / 100)

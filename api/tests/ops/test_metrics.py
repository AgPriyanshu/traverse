from api.ops.metrics import COST_TABLE, estimate_cost_usd


def test_known_model_returns_a_number() -> None:
    cost = estimate_cost_usd(
        "Qwen/Qwen3-8B-AWQ", input_tokens=1_000_000, output_tokens=0
    )

    assert cost is not None
    assert cost > 0


def test_unknown_model_returns_none_not_zero() -> None:
    # None is the signal a cost dashboard reads as "gap in the table"; 0.0
    # would read as a genuinely free call, which is never true (S2.17).
    assert (
        estimate_cost_usd("some/未知-model", input_tokens=100, output_tokens=50) is None
    )


def test_zero_tokens_costs_zero_for_a_known_model() -> None:
    assert (
        estimate_cost_usd("Qwen/Qwen3-8B-AWQ", input_tokens=0, output_tokens=0) == 0.0
    )


def test_cost_scales_linearly_with_tokens() -> None:
    model = next(iter(COST_TABLE))

    single = estimate_cost_usd(model, input_tokens=1000, output_tokens=1000)
    double = estimate_cost_usd(model, input_tokens=2000, output_tokens=2000)

    assert single is not None and double is not None
    assert double == single * 2

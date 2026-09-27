from eval.latency_metrics import (
    P95_BUDGET_MS,
    TTFT_BUDGET_MS,
    LatencySample,
    budget_violations,
    percentile,
    sample_from_query_log_row,
    summarize,
)


def test_percentile_matches_hand_computed_linear_interpolation():
    values = [10.0, 20.0, 30.0, 40.0, 50.0]

    assert percentile(values, 0.0) == 10.0
    assert percentile(values, 1.0) == 50.0
    assert percentile(values, 0.5) == 30.0
    assert percentile([], 0.5) is None
    assert percentile([42.0], 0.95) == 42.0


def test_summarize_computes_total_and_ttft_percentiles_separately():
    samples = [
        LatencySample(total_ms=1000, ttft_ms=200),
        LatencySample(total_ms=2000, ttft_ms=None),
        LatencySample(total_ms=3000, ttft_ms=400),
    ]
    summary = summarize(samples)

    assert summary.sample_count == 3
    assert summary.total.n == 3
    assert summary.ttft.n == 2
    assert summary.total.p50 == 2000
    assert summary.ttft.p50 == 300


def test_p95_within_budget_flags_a_breach():
    # A single outlier in 20 samples lands inside the p95 interpolation gap
    # (rank 18.05 of 19) and barely moves the percentile -- two slow samples
    # actually land the interpolated p95 on the breaching value.
    samples = [LatencySample(total_ms=ms) for ms in [1000] * 18 + [7000] * 2]
    summary = summarize(samples)

    assert summary.p95_within_budget is False
    violations = budget_violations(summary)
    assert any("p95 latency" in v for v in violations)


def test_p95_within_budget_passes_when_every_sample_is_fast():
    samples = [LatencySample(total_ms=1500, ttft_ms=500) for _ in range(20)]
    summary = summarize(samples)

    assert summary.p95_within_budget is True
    assert summary.ttft_p95_within_budget is True
    assert budget_violations(summary) == []


def test_no_samples_is_not_a_silent_pass():
    summary = summarize([])

    assert summary.p95_within_budget is None
    assert budget_violations(summary) == ["no samples — the gate cannot pass on zero questions"]


def test_per_stage_percentiles_grouped_by_stage_name():
    samples = [
        LatencySample(total_ms=1000, stages={"retrieve": 300, "generate": 600}),
        LatencySample(total_ms=2000, stages={"retrieve": 500, "generate": 1200}),
    ]
    summary = summarize(samples)

    assert summary.per_stage["retrieve"].p50 == 400
    assert summary.per_stage["generate"].p50 == 900


def test_sample_from_query_log_row_reads_total_and_ttft_keys():
    row = {"latency_ms": {"total": 4200, "ttft": 600, "retrieve": 800}, "cost_usd": 0.02}
    sample = sample_from_query_log_row(row)

    assert sample.total_ms == 4200
    assert sample.ttft_ms == 600
    assert sample.stages == {"retrieve": 800}
    assert sample.cost_usd == 0.02


def test_sample_from_query_log_row_sums_stages_when_no_total_key():
    row = {"latency_ms": {"route": 100, "retrieve": 300, "generate": 900}}
    sample = sample_from_query_log_row(row)

    assert sample.total_ms == 1300
    assert sample.ttft_ms is None


def test_sample_from_query_log_row_is_none_without_latency_data():
    assert sample_from_query_log_row({"latency_ms": None}) is None
    assert sample_from_query_log_row({}) is None


def test_budgets_match_prd_nfr_perf():
    assert P95_BUDGET_MS == 6_000
    assert TTFT_BUDGET_MS == 1_500

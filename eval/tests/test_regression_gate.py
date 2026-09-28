import pytest

from eval.regression_gate import evaluate_gate, render_report

BASELINE = {
    "extraction_f1": 0.70,
    "relation_f1": 0.42,
    "answer_accuracy": 0.90,
    "citation_precision": 0.95,
}


def test_identical_metrics_pass():
    result = evaluate_gate(dict(BASELINE), BASELINE)

    assert result.passed
    assert not result.regressions


def test_small_improvement_passes():
    current = {**BASELINE, "answer_accuracy": 0.95}
    result = evaluate_gate(current, BASELINE)

    assert result.passed


def test_a_drop_within_threshold_passes():
    current = {**BASELINE, "answer_accuracy": 0.885}  # -1.5 points
    result = evaluate_gate(current, BASELINE)

    assert result.passed


def test_a_deliberately_degraded_answer_accuracy_fails_the_gate():
    # The demo script's exact scenario: "open a PR degrading retrieval -> CI
    # fails with the metric delta." A 10-point drop must fail, loudly, with
    # the offending metric and its delta reported.
    current = {**BASELINE, "answer_accuracy": 0.80}
    result = evaluate_gate(current, BASELINE)

    assert not result.passed
    assert len(result.regressions) == 1
    regression = result.regressions[0]
    assert regression.name == "answer_accuracy"
    assert regression.delta == pytest.approx(-0.10)


def test_a_degraded_relation_f1_also_fails_the_gate():
    # devops-1.md: "Extend it to relation F1 and citation precision" -- not
    # only answer accuracy.
    current = {**BASELINE, "relation_f1": 0.30}
    result = evaluate_gate(current, BASELINE)

    assert not result.passed
    assert {d.name for d in result.regressions} == {"relation_f1"}


def test_a_degraded_citation_precision_also_fails_the_gate():
    current = {**BASELINE, "citation_precision": 0.70}
    result = evaluate_gate(current, BASELINE)

    assert not result.passed
    assert {d.name for d in result.regressions} == {"citation_precision"}


def test_multiple_regressions_are_all_reported():
    current = {**BASELINE, "answer_accuracy": 0.5, "relation_f1": 0.1}
    result = evaluate_gate(current, BASELINE)

    assert not result.passed
    assert {d.name for d in result.regressions} == {"answer_accuracy", "relation_f1"}


def test_a_missing_current_value_is_not_treated_as_a_regression():
    # citation_precision routinely comes back None in an environment with no
    # frontier judge configured -- that must never fail a PR for a reason no
    # author on that PR could fix.
    current = {**BASELINE, "citation_precision": None}
    result = evaluate_gate(current, BASELINE)

    assert result.passed
    citation_delta = next(d for d in result.deltas if d.name == "citation_precision")
    assert not citation_delta.regressed
    assert citation_delta.delta is None


def test_a_missing_baseline_is_not_treated_as_a_regression():
    baseline = {**BASELINE, "relation_f1": None}
    current = {**BASELINE, "relation_f1": 0.05}
    result = evaluate_gate(current, baseline)

    assert result.passed


def test_a_real_regression_with_a_valid_override_passes_but_is_flagged():
    current = {**BASELINE, "answer_accuracy": 0.5}
    result = evaluate_gate(
        current, BASELINE, override_reason="Known trade-off for S8.3 calibration; see PR #123."
    )

    assert result.passed
    assert result.overridden
    assert "S8.3" in result.override_reason


def test_an_empty_override_reason_does_not_bypass_the_gate():
    # A CI job cannot silently pass `--override-reason ""` and get a free
    # pass -- the override must be an actual written justification.
    current = {**BASELINE, "answer_accuracy": 0.5}
    result = evaluate_gate(current, BASELINE, override_reason="   ")

    assert not result.passed
    assert not result.overridden


def test_render_report_names_the_regressed_metric_and_its_delta():
    current = {**BASELINE, "answer_accuracy": 0.70}
    result = evaluate_gate(current, BASELINE)
    report = render_report(result)

    assert "answer_accuracy" in report
    assert "FAIL" in report
    assert "-0.200" in report


def test_render_report_on_a_passing_gate():
    result = evaluate_gate(dict(BASELINE), BASELINE)
    report = render_report(result)

    assert "PASS" in report

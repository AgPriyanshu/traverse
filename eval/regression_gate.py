from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_THRESHOLD_POINTS = 0.02  # 2 points, PRD F6.4

# A metric a PR could not even measure (e.g. citation precision with no
# frontier judge configured) must never be compared against a real baseline
# number as though it were a measured zero -- that would fail every PR in an
# environment with no frontier key, for a reason no author could fix.
TRACKED_METRICS = ("extraction_f1", "relation_f1", "answer_accuracy", "citation_precision")


@dataclass(frozen=True)
class MetricDelta:
    name: str
    baseline: float | None
    current: float | None
    delta: float | None
    regressed: bool
    reason: str | None = None


@dataclass(frozen=True)
class GateResult:
    passed: bool
    deltas: list[MetricDelta] = field(default_factory=list)
    overridden: bool = False
    override_reason: str | None = None

    @property
    def regressions(self) -> list[MetricDelta]:
        return [d for d in self.deltas if d.regressed]


def _compare_one(name: str, baseline: float | None, current: float | None, threshold: float) -> MetricDelta:
    if baseline is None:
        return MetricDelta(name, baseline, current, None, False, reason="no baseline yet")
    if current is None:
        return MetricDelta(
            name, baseline, current, None, False,
            reason="not measurable this run (e.g. missing frontier judge) -- not treated as a regression",
        )

    delta = current - baseline
    regressed = delta < -threshold

    return MetricDelta(name, baseline, current, delta, regressed)


def evaluate_gate(
    current: dict[str, float | None],
    baseline: dict[str, float | None],
    *,
    threshold: float = DEFAULT_THRESHOLD_POINTS,
    override_reason: str | None = None,
) -> GateResult:
    """Compare every tracked metric and decide pass/fail.

    Args:
        current: This run's metric values, keyed by ``TRACKED_METRICS``.
        baseline: The stored baseline's values, same keys.
        threshold: A metric failing by more than this many points regresses
            the gate (PRD default: 0.02, i.e. 2 points).
        override_reason: A non-empty, human-written justification makes the
            gate pass regardless of a real regression (BRANCH.md-style
            documented override) -- an empty or whitespace-only string is
            **not** a valid override and is ignored, so a CI job cannot
            silently bypass the gate by passing ``--override-reason ""``.
    """
    deltas = [
        _compare_one(name, baseline.get(name), current.get(name), threshold)
        for name in TRACKED_METRICS
    ]
    any_regression = any(d.regressed for d in deltas)
    valid_override = bool(override_reason and override_reason.strip())

    passed = (not any_regression) or valid_override

    return GateResult(
        passed=passed,
        deltas=deltas,
        overridden=any_regression and valid_override,
        override_reason=override_reason if valid_override else None,
    )


def render_report(result: GateResult) -> str:
    lines = ["### Regression gate (S8.9, F6.4)", ""]
    lines.append("| Metric | Baseline | Current | Delta | Status |")
    lines.append("| --- | --- | --- | --- | --- |")
    for d in result.deltas:
        baseline_s = f"{d.baseline:.3f}" if d.baseline is not None else "-"
        current_s = f"{d.current:.3f}" if d.current is not None else "-"
        delta_s = f"{d.delta:+.3f}" if d.delta is not None else "-"
        status = "REGRESSED" if d.regressed else (d.reason or "ok")
        lines.append(f"| {d.name} | {baseline_s} | {current_s} | {delta_s} | {status} |")

    lines.append("")
    if result.overridden:
        lines.append(f"**Overridden:** {result.override_reason}")
    elif result.passed:
        lines.append("**Gate: PASS**")
    else:
        names = ", ".join(d.name for d in result.regressions)
        lines.append(f"**Gate: FAIL** -- regressed: {names}")

    return "\n".join(lines) + "\n"

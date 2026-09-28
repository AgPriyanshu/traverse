"""Unit tests for the S8.9 gate's CLI wiring (S8.9, F6.4).

No network: `collect.collect` is exercised with a monkeypatched `_get`/
`resolve_book_id`, same style as `scripts/test_run_ablation.py`. The actual
process exit code (the piece CI depends on) is covered by driving
`check_regression_gate.main` directly against real temp files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import check_regression_gate, collect_gate_metrics


def test_collect_reads_all_four_metrics(monkeypatch):
    monkeypatch.setattr(collect_gate_metrics, "resolve_book_id", lambda *a, **k: "book-1")

    responses = {
        "/api/ops/extraction-quality?book_id=book-1": {"gold_available": True, "roster_f1": 0.70},
        "/api/ops/relation-quality?book_id=book-1": {"gold_available": True, "f1": 0.42},
        "/api/ops/answer-quality?book_key=pride-and-prejudice": {
            "gold_available": True,
            "answered": 30,
            "accuracy": {"rate": 0.9},
            "citation_precision": {"rate": 0.95},
        },
    }
    monkeypatch.setattr(collect_gate_metrics, "_get", lambda base, path: responses[path])

    metrics = collect_gate_metrics.collect("http://x", "pride-and-prejudice")

    assert metrics == {
        "extraction_f1": 0.70,
        "relation_f1": 0.42,
        "answer_accuracy": 0.9,
        "citation_precision": 0.95,
    }


def test_collect_leaves_metrics_none_when_no_gold_set(monkeypatch):
    monkeypatch.setattr(collect_gate_metrics, "resolve_book_id", lambda *a, **k: "book-1")
    monkeypatch.setattr(
        collect_gate_metrics,
        "_get",
        lambda base, path: {"gold_available": False},
    )

    metrics = collect_gate_metrics.collect("http://x", "no-gold-book")

    assert all(v is None for v in metrics.values())


def test_collect_handles_an_uningested_book(monkeypatch):
    monkeypatch.setattr(collect_gate_metrics, "resolve_book_id", lambda *a, **k: None)
    monkeypatch.setattr(
        collect_gate_metrics,
        "_get",
        lambda base, path: {"gold_available": False},
    )

    metrics = collect_gate_metrics.collect("http://x", "not-ingested")

    assert all(v is None for v in metrics.values())


def test_load_metrics_missing_file_is_all_none(tmp_path):
    metrics = check_regression_gate.load_metrics(str(tmp_path / "does-not-exist.json"))

    assert all(v is None for v in metrics.values())


def test_main_exits_zero_on_a_passing_gate(tmp_path, capsys):
    baseline = {"extraction_f1": 0.70, "relation_f1": 0.42, "answer_accuracy": 0.9, "citation_precision": 0.95}
    current = dict(baseline)

    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    baseline_path.write_text(json.dumps(baseline))
    current_path.write_text(json.dumps(current))

    exit_code = _run_main(["--current", str(current_path), "--baseline", str(baseline_path)])

    assert exit_code == 0
    assert "PASS" in capsys.readouterr().out


def test_main_exits_one_on_a_real_regression(tmp_path, capsys):
    baseline = {"extraction_f1": 0.70, "relation_f1": 0.42, "answer_accuracy": 0.9, "citation_precision": 0.95}
    current = {**baseline, "answer_accuracy": 0.5}

    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    baseline_path.write_text(json.dumps(baseline))
    current_path.write_text(json.dumps(current))

    exit_code = _run_main(["--current", str(current_path), "--baseline", str(baseline_path)])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "answer_accuracy" in out


def test_main_with_override_reason_exits_zero_despite_a_regression(tmp_path):
    baseline = {"extraction_f1": 0.70, "relation_f1": 0.42, "answer_accuracy": 0.9, "citation_precision": 0.95}
    current = {**baseline, "answer_accuracy": 0.5}

    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    baseline_path.write_text(json.dumps(baseline))
    current_path.write_text(json.dumps(current))

    exit_code = _run_main(
        [
            "--current", str(current_path),
            "--baseline", str(baseline_path),
            "--override-reason", "Accepted trade-off, see PR description.",
        ]
    )

    assert exit_code == 0


def test_main_writes_the_report_to_out(tmp_path):
    baseline = {"extraction_f1": 0.70, "relation_f1": 0.42, "answer_accuracy": 0.9, "citation_precision": 0.95}
    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    out_path = tmp_path / "report.md"
    baseline_path.write_text(json.dumps(baseline))
    current_path.write_text(json.dumps(baseline))

    _run_main(
        ["--current", str(current_path), "--baseline", str(baseline_path), "--out", str(out_path)]
    )

    assert out_path.exists()
    assert "Regression gate" in out_path.read_text()


def _run_main(argv: list[str]) -> int:
    original_argv = sys.argv
    sys.argv = ["check_regression_gate.py", *argv]
    try:
        return check_regression_gate.main()
    finally:
        sys.argv = original_argv

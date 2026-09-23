#!/usr/bin/env python3
"""Render relation-quality and pass-2 cost as one markdown report (S4.14, S4.15).

Calls the running API's ``GET /ops/relation-quality`` and
``GET /ops/relation-cost`` (do1-owned) rather than the database, so a PR job
and a laptop run the same way. Unlike the Sprint 3 extraction report this one
is partly a gate: an evidence-free edge is a structural invariant violation and
exits non-zero, everything else stays informational until Sprint 8 (F6.4).

Usage:
    python3 -m eval.runners.relations --book-key pride-and-prejudice \\
        --api-base-url http://localhost:8000 --out relation-quality-comment.md
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PRECISION_TARGET = 0.90
RECALL_TARGET = 0.80


def _get(api_base_url: str, path: str, *, timeout: float = 60.0) -> Any:
    url = f"{api_base_url.rstrip('/')}{path}"
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read())


def resolve_book_id(api_base_url: str, book_key: str) -> str:
    """The newest ingested book whose title slugifies to ``book_key``."""
    wanted = re.sub(r"[^a-z0-9]+", "-", book_key.lower().replace("_", "-")).strip("-")
    books = _get(api_base_url, "/api/books")
    matches = [
        b
        for b in books
        if re.sub(r"[^a-z0-9]+", "-", b["title"].lower()).strip("-") == wanted
    ]
    if not matches:
        raise LookupError(f"no ingested book matches {book_key!r}")
    matches.sort(key=lambda b: b.get("ingested_at") or "", reverse=True)

    return matches[0]["id"]


def _fmt(value: float | None, *, pct: bool = False) -> str:
    if value is None:
        return "-"

    return f"{value:.1%}" if pct else f"{value:.3f}"


def _delta(current: float | None, baseline: float | None) -> str:
    if current is None or baseline is None:
        return ""
    diff = current - baseline

    return f" ({'+' if diff >= 0 else ''}{diff:.3f})"


def invariant_violations(quality: dict[str, Any]) -> list[str]:
    """Hard failures: things that must be true regardless of model quality."""
    problems = []
    if quality.get("evidence_free_edges"):
        problems.append(
            f"{quality['evidence_free_edges']} relations in Postgres have no evidence"
        )
    if quality.get("evidence_free_edges_graph"):
        problems.append(
            f"{quality['evidence_free_edges_graph']} Neo4j edges have no evidence"
        )

    return problems


def render_markdown(
    quality: dict[str, Any],
    cost: dict[str, Any] | None,
    baseline: dict[str, Any] | None = None,
) -> str:
    """The PR-comment body, with a delta column when a baseline is given."""
    lines = ["### Relation quality (S4.14)", ""]
    problems = invariant_violations(quality)
    if problems:
        lines += ["**INVARIANT VIOLATED: " + "; ".join(problems) + "**", ""]
    else:
        graph = quality.get("evidence_free_edges_graph")
        lines += [
            "Evidence-free edges: **0** in Postgres"
            + (" and 0 in Neo4j" if graph == 0 else " (graph not checked)"),
            "",
        ]

    if not quality.get("gold_available"):
        reason = quality.get("error") or "no gold relations for this book"
        lines.append(f"_Quality skipped: {reason}._")
    else:
        base = baseline or {}
        rows = [
            ("Precision", "precision", True),
            ("Recall", "recall", True),
            ("F1", "f1", False),
            ("Spurious edge rate", "spurious_edge_rate", True),
            ("Direction accuracy", "direction_accuracy", True),
            ("Temporal arc accuracy", "temporal_arc_accuracy", True),
        ]
        lines += [
            f"Book `{quality.get('book_key')}` · targets P >= {PRECISION_TARGET:.0%}, "
            f"R >= {RECALL_TARGET:.0%} (PRD 1.3)",
            "",
            "| Metric | Current | Baseline (delta) |",
            "| --- | --- | --- |",
        ]
        for label, key, pct in rows:
            cur, prev = quality.get(key), base.get(key)
            lines.append(
                f"| {label} | {_fmt(cur, pct=pct)} | {_fmt(prev, pct=pct)}"
                f"{_delta(cur, prev)} |"
            )

        lines += [
            "",
            "| Predicate | TP | FP | FN | P | R | F1 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in quality.get("per_predicate", []):
            lines.append(
                f"| {row['predicate']} | {row['true_positives']} | "
                f"{row['false_positives']} | {row['false_negatives']} | "
                f"{_fmt(row['precision'])} | {_fmt(row['recall'])} | {_fmt(row['f1'])} |"
            )

        lines += [
            "",
            f"Temporal: {quality.get('temporal_correct', 0)}/"
            f"{quality.get('temporal_transitions', 0)} transitions on chapter, "
            f"{quality.get('arcs_fully_correct', 0)}/{quality.get('arcs_total', 0)} "
            "arcs fully correct.",
        ]
        if quality.get("direction_errors"):
            lines.append("Reversed: " + "; ".join(quality["direction_errors"]))
        if quality.get("spurious_edges"):
            lines.append("Spurious: " + "; ".join(quality["spurious_edges"][:10]))
        if quality.get("missed_gold"):
            lines.append("Missed: " + "; ".join(quality["missed_gold"][:15]))

        judged = quality.get("citation_judged", 0)
        if judged:
            verdict = "meets" if quality.get("citation_meets_target") else "below"
            lines.append(
                f"Citation page accuracy: {_fmt(quality.get('citation_accuracy'), pct=True)}"
                f" over {judged} judged ({verdict} the 95% / n>=50 bar)."
            )
        else:
            lines.append(
                "Citation page accuracy: no human judgements yet "
                "(`make judge-citations`)."
            )

    lines += ["", "### Pass-2 cost (S4.15)", ""]
    if not cost or not cost.get("stages"):
        lines.append("_No pass-2 stage rows recorded for this book._")
    else:
        api_cost = cost.get("total_cost_usd_api_equivalent")
        lines += [
            f"- tokens in/out: {cost['input_tokens']:,} / {cost['output_tokens']:,}",
            f"- USD: ${cost['total_cost_usd_local']:.4f} local-amortised"
            + (f", ${api_cost:.4f} API-equivalent" if api_cost is not None else ""),
            f"- wall clock: {cost['wall_clock_ms'] / 1000:.0f}s"
            + (
                f" ({cost['wall_clock_ms_per_100_pages'] / 1000:.0f}s / 100 pages)"
                if cost.get("wall_clock_ms_per_100_pages") is not None
                else ""
            ),
        ]
        if cost.get("chunks_processed") is not None:
            lines.append(
                f"- chunks: {cost['chunks_processed']} processed, "
                f"{cost['chunks_skipped']} skipped of {cost['chunks_total']} "
                f"({_fmt(cost.get('prefilter_skip_ratio'), pct=True)} skipped by the prefilter)"
            )
        hit = cost.get("prefix_cache_hit_rate")
        alert = " **ALERT: below 80%**" if cost.get("prefix_cache_alert") else ""
        lines.append(f"- prefix-cache hit rate: {_fmt(hit, pct=True)}{alert}")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--book-id")
    parser.add_argument("--book-key")
    parser.add_argument("--baseline", help="A previously saved JSON report.")
    parser.add_argument("--save-json", help="Save this run's raw JSON here.")
    parser.add_argument("--out", help="Markdown destination; stdout if omitted.")
    args = parser.parse_args()
    if not (args.book_id or args.book_key):
        parser.error("give --book-id or --book-key")

    try:
        book_id = args.book_id or resolve_book_id(args.api_base_url, args.book_key)
        quality = _get(
            args.api_base_url, f"/api/ops/relation-quality?book_id={book_id}"
        )
        cost = _get(args.api_base_url, f"/api/ops/relation-cost?book_id={book_id}")
    except (urllib.error.URLError, LookupError) as exc:
        raise SystemExit(f"relation eval failed: {exc}") from exc

    baseline = json.loads(Path(args.baseline).read_text()) if args.baseline else None
    markdown = render_markdown(quality, cost, baseline)
    if args.out:
        Path(args.out).write_text(markdown)
    else:
        print(markdown)
    if args.save_json:
        Path(args.save_json).write_text(json.dumps({**quality, "cost": cost}, indent=2))

    return 1 if invariant_violations(quality) else 0


if __name__ == "__main__":
    raise SystemExit(main())

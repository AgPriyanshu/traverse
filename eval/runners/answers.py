#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ACCURACY_TARGET = 0.85
CITATION_PRECISION_TARGET = 0.95
ABSTENTION_TARGET = 0.90


def _get(api_base_url: str, path: str, *, timeout: float = 30.0) -> Any:
    url = f"{api_base_url.rstrip('/')}{path}"
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read())


def _fmt(value: float | None, *, pct: bool = False) -> str:
    if value is None:
        return "-"

    return f"{value:.1%}" if pct else f"{value:.3f}"


def _delta(current: float | None, baseline: float | None) -> str:
    if current is None or baseline is None:
        return ""
    diff = current - baseline

    return f" ({'+' if diff >= 0 else ''}{diff:.3f})"


def render_markdown(quality: dict[str, Any], baseline: dict[str, Any] | None = None) -> str:
    lines = ["### Answer quality (S6.14)", ""]

    if not quality.get("gold_available"):
        reason = quality.get("error") or "no gold question set for this book"
        lines.append(f"_Skipped: {reason}._")

        return "\n".join(lines) + "\n"

    total = quality.get("total_gold", 0)
    answered = quality.get("answered", 0)
    if not answered:
        lines += [
            f"0/{total} gold questions judged yet. Run "
            "`make eval-answers BOOK=<book-key>` after ingesting the book.",
        ]

        return "\n".join(lines) + "\n"

    base = baseline or {}
    rows = [
        ("Answer accuracy", "accuracy", ACCURACY_TARGET),
        ("Citation precision", "citation_precision", CITATION_PRECISION_TARGET),
        ("Abstention rate", "abstention", ABSTENTION_TARGET),
        ("Aggregation exact match", "aggregation_exact_match", 1.0),
    ]
    lines += [
        f"{answered}/{total} gold questions judged.",
        "",
        "| Metric | Current | n | Target | Baseline (delta) |",
        "| --- | --- | --- | --- | --- |",
    ]
    for label, key, target in rows:
        rate = quality.get(key) or {}
        prev = (base.get(key) or {}).get("rate")
        cur = rate.get("rate")
        met = "OK" if rate.get("meets_target") else "below"
        lines.append(
            f"| {label} | {_fmt(cur, pct=True)} ({met}) | {rate.get('total', 0)} | "
            f">= {target:.0%} | {_fmt(prev, pct=True)}{_delta(cur, prev)} |"
        )

    if quality.get("per_class"):
        lines += ["", "| Class | Judged | Correct | Accuracy |", "| --- | --- | --- | --- |"]
        for row in quality["per_class"]:
            lines.append(
                f"| {row['qclass']} | {row['judged']} | {row['correct']} | "
                f"{_fmt(row['accuracy'], pct=True)} |"
            )

    if quality.get("aggregation_misses"):
        lines += ["", "**Aggregation misses (not exhaustive):**"]
        for miss in quality["aggregation_misses"][:10]:
            lines.append(
                f"- `{miss['question_id']}`: missing {miss['missing']}, "
                f"extra {miss['extra']}"
            )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--book-key", required=True)
    parser.add_argument("--baseline", help="A previously saved JSON report.")
    parser.add_argument("--save-json", help="Save this run's raw JSON here.")
    parser.add_argument("--out", help="Markdown destination; stdout if omitted.")
    args = parser.parse_args()

    try:
        quality = _get(
            args.api_base_url, f"/api/ops/answer-quality?book_key={args.book_key}"
        )
    except urllib.error.URLError as exc:
        raise SystemExit(f"answer eval failed: {exc}") from exc

    baseline = json.loads(Path(args.baseline).read_text()) if args.baseline else None
    markdown = render_markdown(quality, baseline)
    if args.out:
        Path(args.out).write_text(markdown)
    else:
        print(markdown)
    if args.save_json:
        Path(args.save_json).write_text(json.dumps(quality, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

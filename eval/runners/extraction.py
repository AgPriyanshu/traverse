#!/usr/bin/env python3
"""Render extraction-quality metrics as a PR-comment markdown table (S3.14).

Calls the running API's ``GET /ops/extraction-quality?book_id=``
(do1-owned, ``api/ops/extraction_quality.py``) rather than querying Postgres
directly, so this runs the same way in a PR CI job (against the compose
``ci`` stack) and on a laptop (against a dev stack) with no code path
divergence, and never needs its own DB credentials.

Informational only this sprint (plans/sprint-3/devops-1.md S3.14) — nothing
here exits non-zero on a quality regression. The Sprint 8 gate (F6.4) reuses
`render_markdown`'s numbers, not this script's exit code.

Usage:
    python3 -m eval.runners.extraction --book-id <uuid> \\
        --api-base-url http://localhost:8000 \\
        --baseline .ci-cache/extraction-quality-ai-master.json \\
        --save-json .ci-cache/extraction-quality-pr.json
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

NUMERIC_FIELDS = [
    ("roster_precision", "Roster precision"),
    ("roster_recall", "Roster recall"),
    ("roster_f1", "Roster F1"),
    ("b3_precision", "B3 precision"),
    ("b3_recall", "B3 recall"),
    ("b3_f1", "B3 F1"),
    ("tier_accuracy", "Tier accuracy"),
    ("rejection_precision", "Rejection precision"),
]


def fetch_quality(
    api_base_url: str, book_id: str, *, timeout: float = 30.0
) -> dict[str, Any]:
    """GET the live extraction-quality report for `book_id`.

    Raises:
        urllib.error.HTTPError: On anything but a 200 -- including a 404 for
            an unknown book, deliberately not swallowed here so a CI job
            fails loudly on a wiring mistake rather than silently reporting
            an empty table.
    """
    url = f"{api_base_url.rstrip('/')}/api/ops/extraction-quality?book_id={book_id}"
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read())


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def _delta(current: float | None, baseline: float | None) -> str:
    if current is None or baseline is None:
        return ""

    diff = current - baseline
    sign = "+" if diff >= 0 else ""

    return f" ({sign}{diff:.3f})"


def render_markdown(current: dict[str, Any], baseline: dict[str, Any] | None) -> str:
    """The PR-comment body: current numbers, with a delta column when a
    baseline is given (a diff against `ai-master`'s own last report)."""
    if not current.get("gold_available"):
        reason = current.get("error") or "no gold roster for this book"

        return f"### Extraction quality (S3.14)\n\n_Skipped: {reason}._\n"

    lines = [
        "### Extraction quality (S3.14)",
        "_Informational, not gating until Sprint 8 (F6.4)._",
        "",
        f"Book `{current.get('book_key')}`",
        "",
        "| Metric | Current | Baseline (delta) |",
        "| --- | --- | --- |",
    ]
    for key, label in NUMERIC_FIELDS:
        cur = current.get(key)
        base = baseline.get(key) if baseline else None
        lines.append(f"| {label} | {_fmt(cur)} | {_fmt(base)}{_delta(cur, base)} |")

    lines.append("")
    lines.append(
        f"Roster: {current.get('roster_true_positives', 0)} matched, "
        f"{current.get('roster_false_positives', 0)} extra, "
        f"{current.get('roster_false_negatives', 0)} missed."
    )
    if current.get("wrongly_rejected"):
        lines.append(
            "Wrongly rejected (real characters thrown away): "
            + ", ".join(current["wrongly_rejected"])
        )
    if current.get("cascade_contribution"):
        cascade = ", ".join(
            f"{stage}={count}"
            for stage, count in sorted(current["cascade_contribution"].items())
        )
        lines.append(f"Alias-cascade stage contribution: {cascade}")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--baseline", help="Path to a previously-saved JSON report.")
    parser.add_argument(
        "--save-json",
        help="Where to save this run's raw JSON, for a future --baseline.",
    )
    parser.add_argument("--out", help="Where to write the markdown; stdout if omitted.")
    args = parser.parse_args()

    try:
        current = fetch_quality(args.api_base_url, args.book_id)
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"could not reach {args.api_base_url} -- is the stack up? ({exc})"
        ) from exc

    baseline = json.loads(Path(args.baseline).read_text()) if args.baseline else None
    markdown = render_markdown(current, baseline)

    if args.out:
        Path(args.out).write_text(markdown)
    else:
        print(markdown)

    if args.save_json:
        Path(args.save_json).write_text(json.dumps(current, indent=2))


if __name__ == "__main__":
    main()

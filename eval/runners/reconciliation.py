#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

LINK_PRECISION_TARGET = 0.95
LINK_RECALL_TARGET = 0.90
FALSE_MERGE_TARGET = 0.01
DUPLICATE_TARGET = 0.10


def _get(api_base_url: str, path: str, *, timeout: float = 60.0) -> Any:
    url = f"{api_base_url.rstrip('/')}{path}"
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read())


def resolve_project_id(api_base_url: str, project_slug: str) -> str:
    """Find a project by slug from ``GET /api/projects``."""
    projects = _get(api_base_url, "/api/projects")
    matches = [p for p in projects if p["slug"] == project_slug]
    if not matches:
        raise LookupError(f"no project with slug {project_slug!r}")

    return matches[0]["id"]


def _fmt(value: float | None, *, pct: bool = False) -> str:
    if value is None:
        return "-"

    return f"{value:.1%}" if pct else f"{value:.3f}"


def hard_failures(quality: dict[str, Any]) -> list[str]:
    """The false-merge rate is a hard gate; everything else is informational."""
    problems = []
    rate = quality.get("false_merge_rate")
    if rate is not None and rate > FALSE_MERGE_TARGET:
        problems.append(
            f"false_merge_rate {rate:.1%} exceeds the {FALSE_MERGE_TARGET:.0%} target "
            f"({quality.get('false_merge_pairs', 0)} of {quality.get('linked_pairs', 0)} "
            "linked pairs are two different gold people)"
        )

    return problems


def render_markdown(
    quality: dict[str, Any], order_check: dict[str, Any] | None = None
) -> str:
    lines = ["### Reconciliation quality (S5.14)", ""]

    if not quality.get("gold_available"):
        reason = quality.get("error") or "no gold identity for this project's series"
        lines.append(f"_Quality skipped: {reason}._")
    else:
        lines += [
            f"Project `{quality.get('project_id')}` · series `{quality.get('series_key')}` "
            f"· {quality.get('character_count')} characters across "
            f"{quality.get('book_count')} books",
            "",
            "| Metric | Current | Target |",
            "| --- | --- | --- |",
            f"| Link precision | {_fmt(quality.get('link_precision'), pct=True)} "
            f"| >= {LINK_PRECISION_TARGET:.0%} |",
            f"| Link recall | {_fmt(quality.get('link_recall'), pct=True)} "
            f"| >= {LINK_RECALL_TARGET:.0%} |",
            f"| **False merge rate** | **{_fmt(quality.get('false_merge_rate'), pct=True)}** "
            f"| <= {FALSE_MERGE_TARGET:.0%} (hard gate) |",
            f"| Duplicate rate | {_fmt(quality.get('duplicate_rate'), pct=True)} "
            f"| <= {DUPLICATE_TARGET:.0%} |",
            "",
            f"{quality.get('correctly_linked_pairs', 0)}/{quality.get('linked_pairs', 0)} "
            "predicted links correct, "
            f"{quality.get('missed_link_pairs', 0)}/{quality.get('gold_linked_pairs', 0)} "
            "gold links missed, "
            f"{quality.get('duplicate_characters', 0)}/"
            f"{quality.get('gold_multi_book_characters', 0)} multi-book gold characters "
            "duplicated.",
        ]

    lines += ["", f"Graph checksum: `{quality.get('graph_checksum') or '-'}`"]

    if order_check is not None:
        verdict = "PASS" if order_check.get("checksums_identical") else "FAIL"
        lines += [
            "",
            "### Order independence",
            "",
            f"`{order_check.get('project_id')}` vs `{order_check.get('compare_project_id')}`: "
            f"**{verdict}** (hard gate, exact match required).",
        ]

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--project-id")
    parser.add_argument("--project-slug")
    parser.add_argument(
        "--compare-project-id",
        help="A second project id; runs the order-independence hard gate against it.",
    )
    parser.add_argument("--save-json", help="Save this run's raw JSON here.")
    parser.add_argument("--out", help="Markdown destination; stdout if omitted.")
    args = parser.parse_args()
    if not (args.project_id or args.project_slug):
        parser.error("give --project-id or --project-slug")

    try:
        project_id = args.project_id or resolve_project_id(
            args.api_base_url, args.project_slug
        )
        quality = _get(
            args.api_base_url, f"/api/ops/reconciliation-quality?project_id={project_id}"
        )
        order_check = None
        if args.compare_project_id:
            order_check = _get(
                args.api_base_url,
                f"/api/ops/reconciliation-order-check?project_id={project_id}"
                f"&compare_project_id={args.compare_project_id}",
            )
    except (urllib.error.URLError, LookupError) as exc:
        raise SystemExit(f"reconciliation eval failed: {exc}") from exc

    markdown = render_markdown(quality, order_check)
    if args.out:
        Path(args.out).write_text(markdown)
    else:
        print(markdown)
    if args.save_json:
        Path(args.save_json).write_text(
            json.dumps({**quality, "order_check": order_check}, indent=2)
        )

    failures = hard_failures(quality)
    if order_check is not None and not order_check.get("checksums_identical"):
        failures.append("order-independence check failed: checksums differ")
    if failures:
        for problem in failures:
            print(f"FAIL: {problem}")

        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

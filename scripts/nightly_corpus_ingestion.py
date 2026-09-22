#!/usr/bin/env python3
"""Nightly full-corpus ingestion: wall clock and cost trend (devops-1.md S2.18).

Ingests every book in the real S2.16 corpus (`corpus/manifest.json`, five PRD
§7 novels — up to Anna Karenina at 685 of our own pages) through the live API
and posts wall clock plus `/api/ops/metrics` cost to the run summary. This is
the number PRD NFR-perf (≤25 min / 350pp) is judged on, and devops-1.md is
explicit that it needs a trend line starting Sprint 2, not a single
measurement in Sprint 9.

S3.14/S3.15 extend this same nightly run: for every book with a gold roster
(`eval/gold/**` — Pride and Prejudice, Wuthering Heights, S3.13) it also posts
`GET /ops/extraction-quality` (roster P/R/F1, B3, tier accuracy, rejection
precision) and `GET /ops/extraction-cost` (tokens, dual-rate USD, wall clock
per 100 pages, prefix-cache hit rate) to the same run summary — "full novels"
is this job's whole reason to exist alongside the PR-triggered reduced-set
job (`.github/workflows/extraction-quality.yml`), which stays under 10
minutes precisely by not doing this.

Known limitation, recorded rather than hidden: `.github/workflows/
nightly-corpus.yml` runs this on a GitHub-hosted runner with
`INFERENCE_MODE=api` — there is no GPU there. The wall clock this posts is
therefore an API-inference number, not the local-vLLM number NFR-perf is
ultimately judged on, and `prefix_cache_hit_rate` will read `None` here (no
local vLLM to scrape) even once S3.15's wiring is otherwise exercised. Point
`runs-on` at a GPU-labelled self-hosted runner once one exists (Sprint 9
territory) and this script needs no change.

Like `scripts/test_integration_ingestion.py`, a 501 from the upload endpoint
means be1's S2.1 has not merged into this checkout yet; every book is
reported as skipped and the job still exits 0 rather than failing a nightly
schedule for a dependency this file does not control.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from test_integration_ingestion import _multipart_body, _psql, _request, poll_status

sys.path.insert(0, str(REPO_ROOT))
from eval.loaders import available_gold_books  # noqa: E402

MANIFEST_PATH = REPO_ROOT / "corpus" / "manifest.json"
PROJECT_SLUG = "nightly-corpus"
# NFR-perf's own budget, plus headroom for API-mode latency on a shared host.
PER_BOOK_TIMEOUT_S = 40 * 60


def _log(message: str) -> None:
    print(message, flush=True)


def ensure_project() -> str:
    # See test_integration_ingestion.ensure_fixture_project: SQLAlchemy's
    # native Enum column stores the member NAME ("STANDALONE"), not its value.
    _psql(
        "INSERT INTO project (id, name, slug, kind, roster_version) VALUES "
        f"(gen_random_uuid(), 'Nightly Corpus', '{PROJECT_SLUG}', "
        "'STANDALONE', 0) ON CONFLICT (slug) DO NOTHING;"
    )
    return _psql(f"SELECT id FROM project WHERE slug = '{PROJECT_SLUG}';")


def upload(project_id: str, series_order: int, pdf_path: Path) -> tuple[int, dict]:
    body, boundary = _multipart_body(
        "file", pdf_path.name, pdf_path.read_bytes(), "application/pdf"
    )
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    return _request(
        "POST",
        f"/api/projects/{project_id}/books?series_order={series_order}",
        body=body,
        headers=headers,
    )


def _report_extraction_quality_and_cost(book_key: str, book_id: str) -> list[str]:
    """Best-effort `/ops/extraction-quality` + `/ops/extraction-cost` for one
    gold-labelled book. Never fails the run -- a 4xx/5xx here (e.g. the
    extraction stages genuinely have not landed yet) is reported as a line in
    the summary, not a script exit code, same spirit as the 501-skip above.
    """
    lines = [f"### {book_key}"]

    status_code, quality = _request(
        "GET", f"/api/ops/extraction-quality?book_id={book_id}"
    )
    if status_code != 200:
        lines.append(f"- extraction-quality: HTTP {status_code} {quality}")
    elif not quality.get("gold_available"):
        lines.append(f"- extraction-quality: skipped ({quality.get('error') or 'n/a'})")
    else:
        lines.append(
            "- roster P/R/F1: "
            f"{quality.get('roster_precision', 0):.3f} / "
            f"{quality.get('roster_recall', 0):.3f} / "
            f"{quality.get('roster_f1', 0):.3f}"
        )
        if quality.get("b3_f1") is not None:
            lines.append(
                "- B3 P/R/F1: "
                f"{quality['b3_precision']:.3f} / {quality['b3_recall']:.3f} / "
                f"{quality['b3_f1']:.3f}"
            )
        if quality.get("tier_accuracy") is not None:
            lines.append(f"- tier accuracy: {quality['tier_accuracy']:.3f}")
        if quality.get("rejection_precision") is not None:
            lines.append(f"- rejection precision: {quality['rejection_precision']:.3f}")

    status_code, cost = _request("GET", f"/api/ops/extraction-cost?book_id={book_id}")
    if status_code == 200 and cost.get("stages"):
        local_cost = cost.get("total_cost_usd_local", 0)
        api_cost = cost.get("total_cost_usd_api_equivalent")
        api_note = ""
        if api_cost is not None:
            api_note = f" (${api_cost:.4f} at API-equivalent rate)"
        lines.append(f"- extraction cost: ${local_cost:.4f} local{api_note}")
        if cost.get("prefix_cache_hit_rate") is not None:
            hit_rate = cost["prefix_cache_hit_rate"]
            lines.append(f"- prefix-cache hit rate: {hit_rate:.1%}")

    return lines


def main() -> int:
    if not MANIFEST_PATH.exists():
        _log("FAIL: corpus/manifest.json missing — run `make seed` first.")
        return 1

    manifest = json.loads(MANIFEST_PATH.read_text())
    books = manifest.get("books", {})
    if not books:
        _log("FAIL: manifest has no books.")
        return 1

    project_id = ensure_project()
    _log(f"==> project_id={project_id}")

    rows = ["| Book | Pages | Wall clock | Result |", "|---|---|---|---|"]
    quality_lines: list[str] = []
    ingested_any = False

    for i, key in enumerate(sorted(books), start=1):
        record = books[key]
        pdf_path = REPO_ROOT / record["pdf_path"]
        if not pdf_path.exists():
            _log(f"SKIP {key}: {pdf_path} missing — run `make seed`.")
            rows.append(
                f"| {record['title']} | {record['page_count']} | — | corpus not seeded |"
            )
            continue

        start = time.monotonic()
        status_code, body = upload(project_id, i, pdf_path)
        if status_code == 501:
            _log(
                f"SKIP {key}: upload endpoint not implemented yet ({body.get('detail')})."
            )
            rows.append(
                f"| {record['title']} | {record['page_count']} | — | not merged yet |"
            )
            continue
        if status_code != 202:
            _log(f"FAIL {key}: expected 202, got {status_code}: {body}")
            return 1

        ingested_any = True
        book_id = body["id"]
        final = poll_status(book_id, timeout_s=PER_BOOK_TIMEOUT_S)
        elapsed_s = time.monotonic() - start
        _log(f"{key}: {final['status']} in {elapsed_s:.0f}s")
        rows.append(
            f"| {record['title']} | {record['page_count']} | {elapsed_s:.0f}s | {final['status']} |"
        )
        if final["status"] != "ready":
            for stage in final.get("stages", []):
                if stage.get("state") == "failed":
                    _log(f"      {stage['stage']}: {stage.get('error')}")

        if key in available_gold_books():
            quality_lines.extend(_report_extraction_quality_and_cost(key, book_id))

    report_lines = ["## Nightly corpus ingestion", "", *rows]
    if quality_lines:
        report_lines += [
            "",
            "## Extraction quality and cost (S3.14/S3.15)",
            *quality_lines,
        ]

    if ingested_any:
        status_code, metrics = _request("GET", "/api/ops/metrics")
        if status_code == 200:
            total = metrics.get("total_cost_usd", 0.0)
            report_lines += [
                "",
                f"**Total cost, all runs ever recorded: ${total:.4f}**",
            ]

    report = "\n".join(report_lines)
    _log("\n" + report)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        Path(summary_path).write_text(report + "\n")

    if not ingested_any:
        _log(
            "\nNothing was actually ingested this run (see rows above) — "
            "exiting 0 rather than failing the nightly schedule for a "
            "dependency this script does not control."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

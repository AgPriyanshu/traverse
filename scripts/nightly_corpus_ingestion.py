#!/usr/bin/env python3
"""Nightly full-corpus ingestion: wall clock and cost trend (devops-1.md S2.18).

Ingests every book in the real S2.16 corpus (`corpus/manifest.json`, five PRD
§7 novels — up to Anna Karenina at 685 of our own pages) through the live API
and posts wall clock plus `/api/ops/metrics` cost to the run summary. This is
the number PRD NFR-perf (≤25 min / 350pp) is judged on, and devops-1.md is
explicit that it needs a trend line starting Sprint 2, not a single
measurement in Sprint 9.

Known limitation, recorded rather than hidden: `.github/workflows/
nightly-corpus.yml` runs this on a GitHub-hosted runner with
`INFERENCE_MODE=api` — there is no GPU there. The wall clock this posts is
therefore an API-inference number, not the local-vLLM number NFR-perf is
ultimately judged on. Point `runs-on` at a GPU-labelled self-hosted runner
once one exists (Sprint 9 territory) and this script needs no change.

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

    report_lines = ["## Nightly corpus ingestion", "", *rows]

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

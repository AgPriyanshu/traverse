#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT))

from eval.runners.extraction import fetch_quality, render_markdown  # noqa: E402
from test_integration_ingestion import _multipart_body, _psql, _request  # noqa: E402

BOOK_KEY = "wuthering-heights"
PROJECT_SLUG = "pr-extraction-quality"
EXTRACTION_STAGES = {"pipeline.extract_characters", "pipeline.resolve_aliases"}
POLL_BUDGET_S = 5 * 60
POLL_INTERVAL_S = 5


def _log(message: str) -> None:
    print(message, flush=True)


def ensure_project() -> str:
    _psql(
        "INSERT INTO project (id, name, slug, kind, roster_version) VALUES "
        f"(gen_random_uuid(), 'PR Extraction Quality', '{PROJECT_SLUG}', "
        "'STANDALONE', 0) ON CONFLICT (slug) DO NOTHING;"
    )
    return _psql(f"SELECT id FROM project WHERE slug = '{PROJECT_SLUG}';")


def upload(project_id: str, pdf_path: Path) -> tuple[int, dict]:
    body, boundary = _multipart_body(
        "file", pdf_path.name, pdf_path.read_bytes(), "application/pdf"
    )
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    return _request(
        "POST", f"/api/projects/{project_id}/books", body=body, headers=headers
    )


def wait_for_extraction_stages(book_id: str, *, budget_s: float) -> None:
    """Best-effort: return once both extraction stages are terminal, or the
    budget runs out -- never raises, this is informational only."""
    deadline = time.monotonic() + budget_s
    while time.monotonic() < deadline:
        status_code, status = _request("GET", f"/api/books/{book_id}/status")
        if status_code != 200:
            _log(f"  status check returned {status_code}: {status}")
            return

        stages = {s["stage"]: s["state"] for s in status.get("stages", [])}
        relevant = {stage: stages.get(stage) for stage in EXTRACTION_STAGES}
        terminal_states = ("succeeded", "failed", "skipped")
        if all(state in terminal_states for state in relevant.values()):
            _log(f"  extraction stages terminal: {relevant}")
            return

        _log(f"  waiting on extraction stages: {relevant}")
        time.sleep(POLL_INTERVAL_S)

    _log(f"  budget ({budget_s:.0f}s) exhausted -- scoring whatever exists now.")


def main() -> int:
    pdf_path = REPO_ROOT / "corpus" / "downloads" / f"{BOOK_KEY}.pdf"
    if not pdf_path.exists():
        _log(f"FAIL: {pdf_path} missing -- run `make seed --only {BOOK_KEY}` first.")

        return 1

    project_id = ensure_project()
    _log(f"==> project_id={project_id}")

    status_code, body = upload(project_id, pdf_path)
    if status_code == 501:
        _log("SKIP: upload endpoint not implemented on this checkout yet.")
        Path("extraction-quality-comment.md").write_text(
            "### Extraction quality (S3.14)\n\n"
            "_Skipped: upload endpoint (S2.1) not merged into this checkout yet._\n"
        )

        return 0
    if status_code != 202:
        _log(f"FAIL: expected 202, got {status_code}: {body}")

        return 1

    book_id = body["id"]
    _log(f"==> book_id={book_id}")
    _log(f"    waiting on extraction stages (budget {POLL_BUDGET_S:.0f}s)")
    wait_for_extraction_stages(book_id, budget_s=POLL_BUDGET_S)

    quality = fetch_quality("http://localhost:8000", book_id)
    baseline_path = Path("extraction-quality-baseline.json")
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else None
    markdown = render_markdown(quality, baseline)

    _log("\n" + markdown)
    Path("extraction-quality-comment.md").write_text(markdown)
    Path("extraction-quality-current.json").write_text(json.dumps(quality, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())

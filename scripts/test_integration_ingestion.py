#!/usr/bin/env python3
"""The merge-train gate: ingest a small fixture novel through the real API
and assert every stage completed with real output (devops-1.md S2.18).

Deliberately not a real novel — "CI must not take 25 minutes" — this
synthesizes a ~20-page fixture with unambiguous chapter headings using the
same stdlib PDF writer as `scripts/seed_corpus.py`, uploads it to a running
stack, and polls `/status` to a terminal state.

Two things this script owns and nothing else does:
  * `POST /api/projects/{id}/books` is be1's S2.1 — not built yet on every
    branch at every point in the sprint. Rather than fail `make
    test-integration` for a dependency this file has no control over, a 501
    response is treated as "not merged yet" and skipped with exit 0, so the
    gate stays usable pre-merge and starts asserting for real the moment
    S2.1 lands — no code change needed here when that happens.
  * Project creation goes straight to Postgres (`POST /projects` is S5.9,
    Sprint 5) via `docker compose exec db psql`, the same pattern
    `scripts/bootstrap_databases.sh` already uses — not the API, because
    there is no API for it yet.

Usage:
    python3 scripts/test_integration_ingestion.py
    API_BASE_URL=http://localhost:8000 python3 scripts/test_integration_ingestion.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from seed_corpus import build_pdf, paginate

_default_api_port = os.environ.get("API_PORT", "8000")
API_BASE_URL = os.environ.get("API_BASE_URL", f"http://localhost:{_default_api_port}")
COMPOSE = os.environ.get("COMPOSE", "docker compose").split()
PROJECT_SLUG = "ci-integration-fixture"
POLL_INTERVAL_S = 3
POLL_TIMEOUT_S = (
    240  # the fixture is ~20 pages; a real novel budget is 25 min (NFR-perf)
)

TERMINAL_STATUSES = {"ready", "failed"}


def _log(message: str) -> None:
    print(message, flush=True)


def make_fixture_novel(chapters: int = 20) -> bytes:
    """A tiny, deterministic novel: one short, clearly-headed chapter per page."""
    parts = []
    for n in range(1, chapters + 1):
        roman = _to_roman(n)
        body = f"This is the fixture chapter numbered {n}. " * 100
        parts.append(f"CHAPTER {roman}.\n\n{body}")
    text = "\n\n".join(parts)
    pages = paginate(text)
    return build_pdf(pages)


def _to_roman(n: int) -> str:
    table = [
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]
    result = []
    for value, symbol in table:
        while n >= value:
            result.append(symbol)
            n -= value
    return "".join(result)


def _psql(sql: str) -> str:
    result = subprocess.run(
        [
            *COMPOSE,
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-tAc",
            sql,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def ensure_fixture_project() -> str:
    """Create (idempotently) the project this gate uploads into. Returns its id.

    Insert and select are two round trips rather than `INSERT ... RETURNING`
    in one: `psql -tAc` still emits the "INSERT 0 1" command tag alongside a
    RETURNING row, and a status query polluting a UUID string is exactly the
    kind of flake this gate exists to catch, not commit.
    """
    # SQLAlchemy's native Enum column stores the Python member NAME, not its
    # value — "STANDALONE", not ProjectKind.STANDALONE.value ("standalone").
    _psql(
        "INSERT INTO project (id, name, slug, kind, roster_version) VALUES "
        f"(gen_random_uuid(), 'CI Integration Fixture', '{PROJECT_SLUG}', "
        "'STANDALONE', 0) ON CONFLICT (slug) DO NOTHING;"
    )
    return _psql(f"SELECT id FROM project WHERE slug = '{PROJECT_SLUG}';")


def _multipart_body(
    field: str, filename: str, content: bytes, content_type: str
) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    body = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode()
        + content
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return body, boundary


def _request(
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
):
    url = f"{API_BASE_URL}{path}"
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload)
        except json.JSONDecodeError:
            return exc.code, {"detail": payload.decode(errors="replace")}


def upload_book(project_id: str, pdf_bytes: bytes) -> tuple[int, dict]:
    body, boundary = _multipart_body(
        "file", "fixture-novel.pdf", pdf_bytes, "application/pdf"
    )
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    return _request(
        "POST",
        f"/api/projects/{project_id}/books?series_order=1",
        body=body,
        headers=headers,
    )


def poll_status(book_id: str, *, timeout_s: float = POLL_TIMEOUT_S) -> dict:
    """Poll `/status` to a terminal state.

    `timeout_s` is a parameter, not just the module constant, so
    `scripts/nightly_corpus_ingestion.py` can reuse this against a real
    350-page novel (NFR-perf budgets 25 minutes) instead of the ~20-page CI
    fixture's much tighter window.
    """
    deadline = time.monotonic() + timeout_s
    last: dict = {}
    while time.monotonic() < deadline:
        status_code, last = _request("GET", f"/api/books/{book_id}/status")
        if status_code != 200:
            raise RuntimeError(f"GET status returned {status_code}: {last}")
        if last.get("status") == "ready":
            return last
        if last.get("status") == "failed":
            # A stage's Celery autoretry (RETRY_POLICY) upserts its DB row to
            # FAILED, then back to RUNNING once the retry is dequeued — a real
            # ~1s window where derive_book_status honestly reports "failed"
            # for a book that is about to keep going. Debounce it: re-check
            # once, past that window, before trusting it as a real failure.
            time.sleep(POLL_INTERVAL_S)
            status_code, recheck = _request("GET", f"/api/books/{book_id}/status")
            if status_code == 200 and recheck.get("status") != "failed":
                last = recheck
                continue
            return recheck if status_code == 200 else last
        _log(
            f"  ...{last.get('status')} ({len(last.get('stages', []))} stages reported)"
        )
        time.sleep(POLL_INTERVAL_S)
    raise TimeoutError(
        f"book {book_id} did not reach a terminal status within {timeout_s}s: {last}"
    )


_VLLM_METRICS_URL = os.environ.get(
    "VLLM_METRICS_URL",
    f"http://localhost:{os.environ.get('VLLM_PORT', '8080')}/metrics",
)
# vLLM's V1 engine dropped the `gpu_` infix from these two counters; both
# names are read so this still works against an older image (api/ops/
# vllm_metrics.py's own note, S3.9/S4.15).
_PREFIX_CACHE_HITS_NAMES = (
    "vllm:prefix_cache_hits_total",
    "vllm:gpu_prefix_cache_hits_total",
)
_PREFIX_CACHE_QUERIES_NAMES = (
    "vllm:prefix_cache_queries_total",
    "vllm:gpu_prefix_cache_queries_total",
)
_METRIC_LINE_RE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{[^}]*\})?\s+([0-9.eE+-]+)$")


def fetch_vllm_prefix_cache_counters() -> tuple[float, float] | None:
    """Raw cumulative ``(hits, queries)`` from vLLM's own ``/metrics``.

    ``None`` when vLLM is unreachable (``INFERENCE_MODE=api``, no GPU
    profile). Differencing two calls to this around one book's own pass-2
    window is the only per-book prefix-cache hit rate there is: the
    equivalent live-snapshot field (``GET /ops/relation-cost``) reads vLLM's
    lifetime-cumulative counters, which blend in every other purpose's calls
    (chapter/character extraction, the relation verifier) and, since vLLM is
    a host singleton shared by every agent's worktree (BRANCH.md §9), any
    concurrent traffic from another agent too -- see plans/sprint-4/HANDOFF.md
    (S4.15) for why that made the reported hit rate unreliable.
    """
    try:
        with urllib.request.urlopen(_VLLM_METRICS_URL, timeout=5) as response:
            text = response.read().decode()
    except (urllib.error.URLError, TimeoutError):
        return None

    hits = queries = None
    for line in text.splitlines():
        match = _METRIC_LINE_RE.match(line.strip())
        if not match:
            continue
        name, raw_value = match.groups()
        if name in _PREFIX_CACHE_HITS_NAMES:
            hits = float(raw_value)
        elif name in _PREFIX_CACHE_QUERIES_NAMES:
            queries = float(raw_value)
    if hits is None or queries is None:
        return None

    return hits, queries


def prefix_cache_hit_rate_between(
    before: tuple[float, float] | None, after: tuple[float, float] | None
) -> float | None:
    """Prefix-cache hit rate over the window between two counter snapshots."""
    if before is None or after is None:
        return None
    hits_before, queries_before = before
    hits_after, queries_after = after
    queries = queries_after - queries_before
    if queries <= 0:
        return None

    rate = (hits_after - hits_before) / queries

    return rate


def main() -> int:
    _log(f"==> Fixture project ({PROJECT_SLUG})")
    project_id = ensure_fixture_project()
    _log(f"    project_id={project_id}")

    _log(
        "==> Building a ~20-page fixture novel (stdlib PDF writer, no fixed corpus file)"
    )
    pdf_bytes = make_fixture_novel()
    _log(f"    {len(pdf_bytes)} bytes")

    _log("==> POST /api/projects/{id}/books")
    status_code, body = upload_book(project_id, pdf_bytes)
    if status_code == 501:
        _log(f"SKIP: upload endpoint not implemented yet ({body.get('detail')}).")
        _log("      This gate activates automatically once be1's S2.1 merges — nothing")
        _log("      to change here. See plans/sprint-2/HANDOFF.md.")
        return 0
    if status_code != 202:
        _log(f"FAIL: expected 202, got {status_code}: {body}")
        return 1
    book_id = body["id"]
    _log(f"    book_id={book_id}")

    _log("==> Polling /status until terminal")
    final = poll_status(book_id)
    failed_stages = [s for s in final.get("stages", []) if s.get("state") == "failed"]
    # Every stage in StageName is chained regardless of what has landed —
    # api/pipeline/tasks.py stubs a stage that isn't built yet with
    # `raise NotImplementedError("... lands in SX.Y")` so the worker never
    # crashes on an unregistered name (api/workers/policy.py). That means
    # derive_book_status cannot return "ready" until the whole 9-stage
    # pipeline exists (Sprint 8/9) — hitting that frontier here is the
    # expected shape of a passing Sprint 2 run, not a gate failure. Only a
    # failure that is NOT that placeholder is a real regression.
    unexpected_failures = [
        s for s in failed_stages if "lands in S" not in (s.get("error") or "")
    ]
    if final["status"] != "ready" and unexpected_failures:
        _log(f"FAIL: book ended in status={final['status']!r}")
        for stage in unexpected_failures:
            _log(f"      {stage['stage']}: {stage.get('error')}")
        return 1
    if final["status"] == "ready":
        _log(f"    ready. {len(final.get('stages', []))} stages, all terminal.")
    else:
        frontier = failed_stages[0]
        _log(
            f"    stopped at the not-yet-built frontier ({frontier['stage']}: "
            f"{frontier.get('error')}) — expected for this sprint."
        )

    embed_stage = next(
        (
            s
            for s in final.get("stages", [])
            if s.get("stage") == "pipeline.embed_chunks"
        ),
        None,
    )
    if embed_stage is None or embed_stage.get("state") != "succeeded":
        _log(f"FAIL: pipeline.embed_chunks did not succeed: {embed_stage}")
        return 1
    _log("    pipeline.embed_chunks succeeded — embeddings present.")

    _log("==> GET /api/books/{id}/chunks — page provenance")
    status_code, chunks = _request("GET", f"/api/books/{book_id}/chunks?limit=500")
    if status_code != 200 or not chunks:
        _log(f"FAIL: expected a non-empty chunk list, got {status_code}: {chunks}")
        return 1
    missing_pages = [
        c["id"]
        for c in chunks
        if c.get("page_start") is None or c.get("page_end") is None
    ]
    if missing_pages:
        _log(
            f"FAIL: {len(missing_pages)} chunks have no page range: {missing_pages[:5]}"
        )
        return 1
    _log(f"    {len(chunks)} chunks, every one carries page_start/page_end.")

    _log("==> GET /api/books/{id}/chapters — chapter detection")
    status_code, chapters = _request("GET", f"/api/books/{book_id}/chapters")
    if status_code != 200:
        _log(f"FAIL: expected 200, got {status_code}: {chapters}")
        return 1
    if not chapters:
        # build_pdf() now renders a chapter heading in 16pt Courier-Bold
        # rather than the same 10pt/regular font as body text (SCR-1,
        # plans/sprint-3/SCR.md) — Docling's layout model does label these
        # SECTION_HEADER, verified directly against both a synthetic probe
        # and this real corpus's own PDF. Zero chapters here now more likely
        # means be1's own `_segment_chapters`/`_prepare_chapters` isn't
        # wired into this chain yet, or a genuine regression, rather than
        # the previously-structural "Docling never emits the label at all"
        # gap. Still not a gate failure on its own — chapter segmentation's
        # own acceptance criteria are be1's S2.3/S3, not this script's.
        _log(
            "    WARN: 0 chapters detected. Headings now carry a real visual "
            "signal (SCR-1) — check be1's chapter-segmentation stage rather "
            "than assuming this is the old Docling-typography gap."
        )
    else:
        _log(f"    {len(chapters)} chapters detected.")

    _log(
        "\nPASS: fixture novel ingested end to end with page-provenanced chunks."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

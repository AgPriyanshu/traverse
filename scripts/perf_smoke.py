#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eval.latency_metrics import LatencySample, budget_violations, summarize  # noqa: E402

_default_api_port = os.environ.get("API_PORT", "8000")
API_BASE_URL = os.environ.get("API_BASE_URL", f"http://localhost:{_default_api_port}")
COMPOSE = os.environ.get("COMPOSE", "docker compose").split()
PROJECT_SLUG = os.environ.get("PERF_SMOKE_PROJECT_SLUG", "ci-integration-fixture")
QUESTION_COUNT = 20


def _log(message: str) -> None:
    print(message, flush=True)


def _psql(sql: str) -> str:
    result = subprocess.run(
        [*COMPOSE, "exec", "-T", "db", "psql", "-U", "postgres", "-d", "postgres", "-tAc", sql],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def resolve_project_id() -> str | None:
    project_id = _psql(f"SELECT id FROM project WHERE slug = '{PROJECT_SLUG}';")
    return project_id or None


def _post(path: str, payload: dict, *, timeout: float = 30.0) -> tuple[int, str, float]:
    url = f"{API_BASE_URL}{path}"
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
            return response.status, response.read().decode(errors="replace"), time.monotonic() - start
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace"), time.monotonic() - start


def parse_sse_events(raw: str) -> list[dict]:
    events = []
    for block in raw.split("\n\n"):
        data_lines = [
            line[len("data:") :].strip() for line in block.splitlines() if line.startswith("data:")
        ]
        if not data_lines:
            continue
        try:
            events.append(json.loads("\n".join(data_lines)))
        except json.JSONDecodeError:
            continue

    return events


def ask(project_id: str, question: str) -> tuple[int, LatencySample | None, str | None]:
    """POST /api/query and time it end-to-end, plus TTFT off the raw stream.

    The raw SSE body has already fully arrived by the time ``urlopen``
    returns (no incremental read here), so TTFT is approximated as the first
    ``token`` event's position in the stream scaled by total wall time — a
    coarser measurement than a true first-byte timer, adequate for a smoke
    gate but not for the trended dashboard, which reads the pipeline's own
    ``latency_ms.ttft`` from ``QueryLog`` via ``GET /ops/query-latency``.
    """
    status_code, raw, elapsed_s = _post(
        "/api/query", {"project_id": project_id, "question": question}
    )
    if status_code != 200:
        try:
            detail = json.loads(raw).get("detail", raw)
        except json.JSONDecodeError:
            detail = raw

        return status_code, None, detail

    events = parse_sse_events(raw)
    total_ms = elapsed_s * 1000
    first_token_index = next(
        (i for i, e in enumerate(events) if e.get("type") == "token"), None
    )
    ttft_ms = (
        total_ms * (first_token_index / len(events))
        if first_token_index is not None and events
        else None
    )
    done = next((e for e in events if e.get("type") == "done"), {})
    reported_latency = done.get("latency_ms") or {}
    if isinstance(reported_latency, dict) and reported_latency.get("total") is not None:
        total_ms = float(reported_latency["total"])
    if isinstance(reported_latency, dict) and reported_latency.get("ttft") is not None:
        ttft_ms = float(reported_latency["ttft"])

    return status_code, LatencySample(total_ms=total_ms, ttft_ms=ttft_ms), None


def main() -> int:
    waiver = os.environ.get("PERF_SMOKE_WAIVE")
    enforcing = os.environ.get("INTEGRATION_HOST") == "1"

    if not enforcing:
        _log(
            "INTEGRATION_HOST != 1 -- reporting only, not gating. Per BRANCH.md §9 a "
            "worktree shares the GPU and cannot produce a valid timing."
        )
    if waiver:
        _log(f"PERF_SMOKE_WAIVE set: {waiver!r} -- gate will not fail the build this run.")

    project_id = resolve_project_id()
    if not project_id:
        _log(f"SKIP: no project with slug {PROJECT_SLUG!r} -- run test-integration first.")
        return 0

    samples: list[LatencySample] = []
    for n in range(1, QUESTION_COUNT + 1):
        question = f"What happens on page {n} of the book?"
        status_code, sample, detail = ask(project_id, question)
        if status_code == 501:
            _log(f"SKIP: /api/query not implemented yet ({detail}).")
            return 0
        if status_code != 200:
            _log(f"[{n}/{QUESTION_COUNT}] FAIL: HTTP {status_code}: {detail}")
            continue

        samples.append(sample)
        ttft = f"{sample.ttft_ms:.0f}ms" if sample.ttft_ms is not None else "n/a"
        _log(f"[{n}/{QUESTION_COUNT}] total={sample.total_ms:.0f}ms ttft={ttft}")

    summary = summarize(samples)
    violations = budget_violations(summary)

    _log("")
    _log(
        f"n={summary.sample_count} total p50/p95/p99="
        f"{summary.total.p50}/{summary.total.p95}/{summary.total.p99}ms  "
        f"ttft p50/p95/p99={summary.ttft.p50}/{summary.ttft.p95}/{summary.ttft.p99}ms"
    )

    if not violations:
        _log("PASS: within the NFR-perf budget (p95 <= 6000ms, TTFT p95 <= 1500ms).")
        return 0

    for v in violations:
        _log(f"BUDGET BREACH: {v}")

    if not enforcing or waiver:
        _log("Not failing the build (report-only host or waived).")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Run the Sprint 8 ablation matrix and publish one run's results (S8.8, F6.3).

This is a **partial** matrix by design (`plans/sprint-8/README.md`): one axis
varied against the recommended value of the other two, never the full
extraction x retrieval x model cross product (30+ full-novel runs). Cells
that need a configuration this codebase cannot yet produce -- no ablation
config-switch exists (F6.3/S8.2, be2) and no non-judge frontier/routed
answering path exists in `api/llm/routing.py` -- are recorded as
``status: "blocked"`` with the specific reason, never silently skipped or
left to read as a zero.

Reproducibility: every run records its git SHA, each book's pinned
``pdf_sha256`` (from `corpus/manifest.json`, the same pin `eval/loaders.py`
enforces) and the local model id, so a published number can be regenerated a
month later or shown to be stale.

Caching: a cell's result is cached on ``eval.ablation.cache_key`` (config +
book + corpus checksum + git SHA) under ``eval/ablation_runs/cache/`` --
identical inputs are never rescored.

Resumability: a run's per-cell progress is written to
``eval/ablation_runs/<run-id>/state.json`` after every cell. Re-invoking with
the same ``--run-id`` skips whatever that file already marks done, so a run
that dies on cell N does not restart at cell 1.

Persistence: writes one ``EvalRun`` + N ``EvalResult`` rows (migration 0011)
via a direct DB session -- run this inside the api container/image, where
``PYTHONPATH=/app`` and ``POSTGRES_DB_STRING`` point at the real database
(`make eval-ablation`, mirroring `api.ops.graph_rebuild`'s pattern). Pass
``--no-persist`` to skip the DB write and only produce the JSON artifact,
which needs no container.

Usage:
    python3 scripts/run_ablation.py --run-id 2026-09-28
    python3 scripts/run_ablation.py --run-id 2026-09-28 --force   # ignore cache
    python3 scripts/run_ablation.py --run-id 2026-09-28 --no-persist
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eval.ablation import (
    BLOCKED_FRONTIER_JUDGE,
    AblationCell,
    build_matrix,
    cache_key,
    metrics_from_answer_quality,
    metrics_from_extraction_quality,
)

MANIFEST_PATH = REPO_ROOT / "corpus" / "manifest.json"
OUT_ROOT = REPO_ROOT / "eval" / "ablation_runs"
CACHE_DIR = OUT_ROOT / "cache"
LATEST_PATH = OUT_ROOT / "latest.json"

# Only these two books have an S3.13 gold roster (extraction axis); only
# Pride and Prejudice has an S6.14 gold answer set (retrieval/model axes).
EXTRACTION_BOOKS = ["pride-and-prejudice", "wuthering-heights"]
ANSWER_BOOK = "pride-and-prejudice"


def _log(message: str) -> None:
    print(message, flush=True)


def _get(api_base_url: str, path: str, *, timeout: float = 60.0) -> dict[str, Any]:
    url = f"{api_base_url.rstrip('/')}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.URLError as exc:
        return {"_transport_error": str(exc)}


def git_sha() -> str | None:
    """``$GIT_SHA`` first -- the api image ships no ``.git`` and no ``git``
    binary (``api/Dockerfile`` copies source only), so ``make eval-ablation``
    (which runs this inside that container) passes the host's SHA through the
    environment. Falls back to a real ``git`` invocation for host/CI runs
    where ``.git`` is actually present."""
    env_sha = os.environ.get("GIT_SHA")
    if env_sha:
        return env_sha

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )

        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text())


def corpus_checksum(manifest: dict[str, Any], book_key: str) -> str | None:
    entry = manifest.get("books", {}).get(book_key)

    return entry.get("pdf_sha256") if entry else None


def _slugify_title(title: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def resolve_book_id(api_base_url: str, book_key: str) -> str | None:
    """``GET /api/books``, matched by the same slug ``api/ops/relation_quality.py``
    derives from ``Book.title`` -- there is no dedicated book-key lookup route."""
    books = _get(api_base_url, "/api/books")
    if not isinstance(books, list):
        return None

    candidates = [b for b in books if _slugify_title(b.get("title", "")) == book_key]
    if not candidates:
        return None

    candidates.sort(key=lambda b: b.get("ingested_at") or "", reverse=True)

    return candidates[0]["id"]


def load_state(state_path: Path) -> dict[str, Any]:
    if state_path.exists():
        return json.loads(state_path.read_text())

    return {}


def save_state(state_path: Path, state: dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True))


def load_cache(key: str) -> dict[str, Any] | None:
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())

    return None


def save_cache(key: str, payload: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(json.dumps(payload, indent=2, sort_keys=True))


def blocked_result(cell: AblationCell) -> dict[str, Any]:
    return {
        "status": "blocked",
        "blocked_reason": cell.blocked_reason,
        "metrics": {"sample_size": 0},
    }


def measure_extraction_cell(
    api_base_url: str, cell: AblationCell, manifest: dict[str, Any], *, force: bool
) -> list[dict[str, Any]]:
    """One result per gold-labelled book -- the only configuration this
    pipeline can currently produce is ``RECOMMENDED_EXTRACTION``."""
    results = []
    sha = git_sha()
    for book_key in EXTRACTION_BOOKS:
        checksum = corpus_checksum(manifest, book_key)
        key = cache_key(cell, book_key=book_key, corpus_checksum=checksum or "", git_sha=sha or "")
        cached = None if force else load_cache(key)
        if cached is not None:
            _log(f"  [{cell.label}] {book_key}: cached")
            results.append({**cached, "book_key": book_key, "cache_key": key})
            continue

        book_id = resolve_book_id(api_base_url, book_key)
        if book_id is None:
            payload = {
                "status": "blocked",
                "blocked_reason": f"blocked: {book_key} is not ingested in this environment",
                "metrics": {"sample_size": 0},
            }
        else:
            quality = _get(api_base_url, f"/api/ops/extraction-quality?book_id={book_id}")
            if not quality.get("gold_available"):
                payload = {
                    "status": "blocked",
                    "blocked_reason": f"blocked: no gold roster for {book_key}",
                    "metrics": {"sample_size": 0},
                }
            else:
                payload = {"status": "measured", "blocked_reason": None, "metrics": metrics_from_extraction_quality(quality)}

        save_cache(key, payload)
        _log(f"  [{cell.label}] {book_key}: {payload['status']}")
        results.append({**payload, "book_key": book_key, "cache_key": key})

    return results


def measure_answer_backed_cell(
    api_base_url: str, cell: AblationCell, manifest: dict[str, Any], *, force: bool
) -> list[dict[str, Any]]:
    """Retrieval/model recommended cells share the one live query configuration
    -- there is nothing yet that distinguishes "retrieval=graph_constrained"
    from "model=local" at the measurement layer, since both describe the same
    (and only) code path. Both axes read the same S6.14 answer-quality run."""
    sha = git_sha()
    checksum = corpus_checksum(manifest, ANSWER_BOOK)
    key = cache_key(cell, book_key=ANSWER_BOOK, corpus_checksum=checksum or "", git_sha=sha or "")
    cached = None if force else load_cache(key)
    if cached is not None:
        _log(f"  [{cell.label}] {ANSWER_BOOK}: cached")
        return [{**cached, "book_key": ANSWER_BOOK, "cache_key": key}]

    quality = _get(api_base_url, f"/api/ops/answer-quality?book_key={ANSWER_BOOK}")
    if not quality.get("gold_available"):
        payload = {
            "status": "blocked",
            "blocked_reason": f"blocked: no gold answer set for {ANSWER_BOOK}",
            "metrics": {"sample_size": 0},
        }
    else:
        metrics = metrics_from_answer_quality(quality)
        partial_note = None
        if quality.get("answered", 0) < quality.get("total_gold", 0):
            partial_note = (
                f"partial run: {quality.get('answered', 0)}/{quality.get('total_gold', 0)} "
                "gold questions answered"
            )
        if metrics.get("accuracy") is None and metrics.get("precision") is None:
            payload = {
                "status": "partial" if partial_note else "blocked",
                "blocked_reason": partial_note or BLOCKED_FRONTIER_JUDGE,
                "metrics": metrics,
            }
            if partial_note:
                payload["blocked_reason"] = f"{BLOCKED_FRONTIER_JUDGE} ({partial_note})"
        else:
            payload = {"status": "measured", "blocked_reason": partial_note, "metrics": metrics}

    save_cache(key, payload)
    _log(f"  [{cell.label}] {ANSWER_BOOK}: {payload['status']}")

    return [{**payload, "book_key": ANSWER_BOOK, "cache_key": key}]


def run_matrix(
    api_base_url: str, *, run_id: str, force: bool
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest = load_manifest()
    matrix = build_matrix()
    state_path = OUT_ROOT / run_id / "state.json"
    state = load_state(state_path)

    cells_out: list[dict[str, Any]] = []
    for cell in matrix:
        cell_id = f"{cell.axis}:{cell.label}"
        if cell_id in state and not force:
            _log(f"[{cell_id}] resuming from state: {state[cell_id]['status']}")
            cells_out.extend(state[cell_id]["results"])
            continue

        _log(f"[{cell_id}]")
        if cell.blocked_reason is not None:
            per_book = [{**blocked_result(cell), "book_key": None, "cache_key": None}]
        elif cell.axis == "extraction":
            per_book = measure_extraction_cell(api_base_url, cell, manifest, force=force)
        else:
            per_book = measure_answer_backed_cell(api_base_url, cell, manifest, force=force)

        row_results = [
            {
                "axis": cell.axis,
                "label": cell.label,
                "recommended": cell.recommended,
                "config": {"axis": cell.axis, "label": cell.label, **cell.config},
                **row,
            }
            for row in per_book
        ]
        state[cell_id] = {"status": "done", "results": row_results}
        save_state(state_path, state)
        cells_out.extend(row_results)

    return cells_out, manifest


async def persist(cells: list[dict[str, Any]], *, corpus_version: str, notes: str) -> str:
    from api.db.engine import db_session
    from api.ops.ablation import record_eval_run

    db_cells = [
        {
            "axis": c["axis"],
            "label": c["label"],
            "book_key": c.get("book_key"),
            "config": c["config"],
            "metrics": c["metrics"],
        }
        for c in cells
    ]
    async with db_session() as session:
        run = await record_eval_run(
            session,
            corpus_version=corpus_version,
            git_sha=git_sha(),
            notes=notes,
            cells=db_cells,
        )

    return str(run.id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--run-id", default=datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ"))
    parser.add_argument("--force", action="store_true", help="ignore the cache and state file")
    parser.add_argument("--no-persist", action="store_true", help="skip the DB write")
    args = parser.parse_args()

    cells, manifest = run_matrix(args.api_base_url, run_id=args.run_id, force=args.force)

    total = len(cells)
    by_status: dict[str, int] = {}
    for c in cells:
        by_status[c["status"]] = by_status.get(c["status"], 0) + 1

    corpus_version = manifest.get("generated_at")
    artifact = {
        "run_id": args.run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "git_sha": git_sha(),
        "corpus_version": corpus_version,
        "summary": {"total_rows": total, **by_status},
        "cells": cells,
    }

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / f"{args.run_id}.json").write_text(json.dumps(artifact, indent=2, sort_keys=True))
    LATEST_PATH.write_text(json.dumps(artifact, indent=2, sort_keys=True))

    _log("")
    _log(f"Run {args.run_id}: {total} rows -- {by_status}")

    if not args.no_persist:
        run_db_id = asyncio.run(
            persist(
                cells,
                corpus_version=corpus_version,
                notes=f"scripts/run_ablation.py --run-id {args.run_id}",
            )
        )
        _log(f"Persisted as EvalRun {run_db_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

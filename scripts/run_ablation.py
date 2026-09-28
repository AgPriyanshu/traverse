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
    BLOCKED_FRONTIER_MODEL,
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

# One gold question's hard wall-clock budget for the direct in-process
# narrative pipeline run (S8.8.1, _run_narrative_gold_set). Not a production
# value -- api/llm/** sets no request timeout anywhere today (checked), so a
# single pathological generation can otherwise stall an entire ablation cell
# indefinitely. Real, reproducible example found running this fast-follow
# against the shared dev stack's CPU-only vLLM: pp-031 ("Who are Mr. and Mrs.
# Gardiner?", class=single_fact -- a graph-derived route with no expected
# narrative generation at all) ran past 3 minutes of continuous, still-
# growing GPU-KV-cache generation before being killed; see
# plans/sprint-8/HANDOFF.md. A question that times out is recorded as
# unanswered for that cell, never a guessed answer.
QUESTION_TIMEOUT_S = 90.0


def _log(message: str) -> None:
    print(message, flush=True)


def _get(api_base_url: str, path: str, *, timeout: float = 60.0) -> dict[str, Any]:
    url = f"{api_base_url.rstrip('/')}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.URLError as exc:
        return {"_transport_error": str(exc)}


def _post_json(
    api_base_url: str, path: str, payload: dict[str, Any], *, timeout: float = 90.0
) -> tuple[int | None, dict[str, Any]]:
    """Used for the judge call only (``/api/ops/judge-answer``, do1-owned) --
    everything else this script needs from the running API is a ``GET``."""
    url = f"{api_base_url.rstrip('/')}{path}"
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except json.JSONDecodeError:
            return exc.code, {}
    except urllib.error.URLError as exc:
        return None, {"_transport_error": str(exc)}


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


def resolve_project_id(api_base_url: str, book_key: str) -> str | None:
    """Same lookup as ``resolve_book_id``, but returns the book's
    ``project_id`` -- what the in-process narrative pipeline run
    (``_run_narrative_gold_set``) needs to build a ``QueryRequest``."""
    books = _get(api_base_url, "/api/books")
    if not isinstance(books, list):
        return None

    candidates = [b for b in books if _slugify_title(b.get("title", "")) == book_key]
    if not candidates:
        return None

    candidates.sort(key=lambda b: b.get("ingested_at") or "", reverse=True)

    return candidates[0]["project_id"]


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


def _build_ablation_config(cell: AblationCell):
    """One ``AblationConfig`` (``api/contracts/api.py``) for ``cell`` --
    ``cell.config``'s keys already match that model's field names one for one
    (``eval/ablation.py``'s own ``build_matrix``), so no translation table."""
    from api.contracts.api import AblationConfig

    return AblationConfig(axis=cell.axis, label=cell.label, **cell.config)


def measure_extraction_cell(
    api_base_url: str, cell: AblationCell, manifest: dict[str, Any], *, force: bool
) -> list[dict[str, Any]]:
    """One result per gold-labelled book -- the only configuration this
    pipeline can currently produce is ``RECOMMENDED_EXTRACTION``.

    Calls ``resolve()`` first, purely as a live canary on the fast-follow's
    documented gap (S8.8.1): the extraction axis has no runtime switch in
    ``api/eval/ablation.py`` (be1/api-review territory, not be2's or this
    script's to build), so ``resolve()`` is expected to raise
    ``AblationAxisNotOwned`` for every extraction cell, including this one --
    that exception is *not* what makes this cell measurable or not (roster
    precision/recall/F1 is read straight off ``/ops/extraction-quality``,
    no retrieval/model switch involved). If ``resolve()`` ever stops raising
    here, an extraction config-switch has landed and this function -- and
    ``eval/ablation.py``'s ``BLOCKED_CONFIG_SWITCH`` rows -- are stale.
    """
    from api.eval.ablation import AblationAxisNotOwned, resolve

    try:
        resolve(_build_ablation_config(cell))
    except AblationAxisNotOwned:
        pass
    else:
        raise AssertionError(
            "api.eval.ablation.resolve() no longer raises AblationAxisNotOwned "
            "for axis='extraction' -- an extraction config-switch has landed. "
            "Update eval/ablation.py's non-recommended extraction rows "
            "(currently BLOCKED_CONFIG_SWITCH) and this function to use it."
        )

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


async def _run_narrative_gold_set(
    api_base_url: str,
    book_key: str,
    *,
    retrieval_mode: Any,
    inference_mode: Any,
) -> dict[str, Any]:
    """Drive every gold question through the real, in-process query pipeline
    once, with ``retrieval_mode``/``inference_mode`` (``ResolvedAblation``,
    ``api/eval/ablation.py::resolve()``) applied to the narrative
    retrieval/generation calls a question happens to take (S8.8.1).

    This replaces reading a shared, already-judged ``answer_judgements.json``
    for every retrieval/model cell: each cell now gets its own real answers,
    not a copy of whichever cell ran first. Only the ``narrative`` route
    (``api/query/pipeline.py::_answer_narrative``) ever calls
    ``retrieve_for_narrative``/``stream_narrative_draft``, so a
    ``relationship``/``path``/``aggregation``/``single_fact`` gold question
    answers identically across every retrieval/model cell, exactly like
    production -- only the subset of questions that actually route to
    ``narrative`` differs cell to cell, which is the true, honest scope of
    these two axes.

    The override is applied by monkeypatching ``api.query.retrieval`` /
    ``api.query.generation`` module attributes for the duration of this call
    and restoring them in a ``finally`` -- ``api/query/pipeline.py`` (be2-
    owned, this script must not edit it) looks these two functions up by
    module attribute at call time, so this reaches every call site
    ``answer_question`` takes without touching a single line of that file,
    exactly the "pass the resolved mode into these two functions directly"
    shape ``api/eval/ablation.py::resolve()``'s own docstring names.
    """
    from uuid import UUID

    from eval.answer_metrics import (
        AnsweredCitation,
        AnsweredQuery,
        JudgeVerdict,
        gold_questions,
        score_answers,
    )
    from eval.loaders import CorpusChecksumMismatch, RosterSchemaError, load_gold_answers

    from api.contracts.api import QueryRequest
    from api.db.engine import db_session
    from api.query import generation as generation_mod
    from api.query import retrieval as retrieval_mod
    from api.query.grounding import ABSTENTION_TEXT
    from api.query.pipeline import answer_question

    try:
        document = load_gold_answers(book_key)
    except FileNotFoundError:
        return {"gold_available": False}
    except (RosterSchemaError, CorpusChecksumMismatch) as exc:
        return {"gold_available": False, "error": str(exc)}

    gold = gold_questions(document)
    sample_limit = os.environ.get("ABLATION_GOLD_SET_LIMIT")
    if sample_limit:
        # Stand-in for a real constraint hit running this fast-follow against
        # this shared dev stack's CPU-only vLLM (no GPU profile up): a full
        # 38-question narrative pass can run into multi-minute single
        # generations (see QUESTION_TIMEOUT_S's docstring). Not a permanent
        # flag -- unset, this measures the real, full gold set, which is what
        # a GPU-backed or more patient run should do. The caller
        # (measure_answer_backed_cell) skips the on-disk cache whenever this
        # is set, so a capped sample can never masquerade as -- or block --
        # a later full run under the same cache key.
        gold = gold[: int(sample_limit)]
        _log(f"    ABLATION_GOLD_SET_LIMIT={sample_limit}: measuring a partial sample, not the full gold set")

    project_id = resolve_project_id(api_base_url, book_key)
    if project_id is None:
        return {"gold_available": False, "error": f"{book_key} is not ingested in this environment"}

    orig_retrieve = retrieval_mod.retrieve_for_narrative
    orig_stream = generation_mod.stream_narrative_draft

    async def _patched_retrieve(*args: Any, **kwargs: Any) -> Any:
        kwargs["mode"] = retrieval_mode

        return await orig_retrieve(*args, **kwargs)

    async def _patched_stream(*args: Any, **kwargs: Any):
        kwargs["mode"] = inference_mode
        async for delta in orig_stream(*args, **kwargs):
            yield delta

    answered: list[AnsweredQuery] = []
    verdicts: list[JudgeVerdict] = []

    retrieval_mod.retrieve_for_narrative = _patched_retrieve
    generation_mod.stream_narrative_draft = _patched_stream
    try:
        for question in gold:
            tokens: list[str] = []
            citations_raw: list[dict[str, Any]] = []
            abstained = False
            request = QueryRequest(project_id=UUID(project_id), question=question.question)

            async def _drive() -> None:
                async with db_session() as session:
                    async for event in answer_question(session, request):
                        etype = getattr(event, "type", None)
                        if etype == "token":
                            tokens.append(event.text)
                        elif etype == "citation":
                            citations_raw.append(event.citation.model_dump(mode="json"))
                        elif etype == "done":
                            nonlocal abstained
                            abstained = event.abstained

            # A fresh session per question, exactly like the real
            # ``get_session`` FastAPI dependency (``api/db/engine.py``) --
            # never one shared session for the whole gold set, so a mid-
            # transaction exception on one question can't poison the next.
            # Bounded by QUESTION_TIMEOUT_S: no request timeout exists
            # anywhere in api/llm/** today, so one pathological generation
            # would otherwise stall the whole cell (see that constant's
            # docstring for the real example this caught).
            try:
                await asyncio.wait_for(_drive(), timeout=QUESTION_TIMEOUT_S)
            except TimeoutError:
                _log(f"    [{question.id}] timed out after {QUESTION_TIMEOUT_S}s -- recorded as unanswered")
                tokens.clear()
                citations_raw.clear()
            except Exception as exc:  # noqa: BLE001 -- mirrors api/routes/query.py::
                # _event_stream's own boundary: a stream that breaks
                # partway through still keeps whatever text/citations it
                # already produced, same as a real client would see.
                _log(f"    [{question.id}] pipeline error after partial output: {exc}")

            answer_text = "".join(tokens) or None
            if answer_text and answer_text.startswith(ABSTENTION_TEXT):
                # A real, pre-existing bug independent of this ablation
                # (api/query/pipeline.py::_finish raises "greenlet_spawn has
                # not been called" while persisting the query log/turn, on
                # every route, in this environment -- see
                # plans/sprint-8/HANDOFF.md) can prevent the `done` event
                # above from ever being yielded. The abstention text is still
                # authoritative regardless: grounding.abstain() always pairs
                # it with citations=[], for both call sites that produce it.
                abstained = True

            if answer_text is None:
                continue

            answered.append(
                AnsweredQuery(
                    question_id=question.id,
                    answer=answer_text,
                    abstained=abstained,
                    citations=tuple(
                        AnsweredCitation(
                            book_id=str(c.get("book_id", "")),
                            page_start=c["page_start"],
                            page_end=c.get("page_end", c["page_start"]),
                            quote=c.get("quote"),
                        )
                        for c in citations_raw
                    ),
                )
            )

            status_code, verdict = _post_json(
                api_base_url,
                "/api/ops/judge-answer",
                {
                    "question_id": question.id,
                    "question": question.question,
                    "expected_answer": question.expected_answer,
                    "expect_abstain": question.expect_abstain,
                    "system_answer": answer_text,
                    "abstained": abstained,
                    "citations": citations_raw,
                },
            )
            if status_code == 200 and verdict:
                verdicts.append(
                    JudgeVerdict(
                        question_id=question.id,
                        correct=verdict.get("correct"),
                        citation_supported=tuple(verdict.get("citation_supported", [])),
                    )
                )
    finally:
        retrieval_mod.retrieve_for_narrative = orig_retrieve
        generation_mod.stream_narrative_draft = orig_stream

    scores = score_answers(gold, answered, verdicts)

    return {
        "gold_available": True,
        "answered": scores.answered,
        "total_gold": scores.total_gold,
        "accuracy": {"rate": scores.accuracy.rate},
        "citation_precision": {"rate": scores.citation_precision.rate},
    }


def measure_answer_backed_cell(
    api_base_url: str, cell: AblationCell, manifest: dict[str, Any], *, force: bool
) -> list[dict[str, Any]]:
    """Resolve this cell's retrieval/model switch (S8.2's ``resolve()``) and
    measure it independently by driving the real gold set through the
    pipeline once with that switch applied -- retrieval and model cells no
    longer share one live run (S8.8.1; see ``_run_narrative_gold_set``)."""
    from api.eval.ablation import AblationAxisNotOwned, resolve

    # A capped sample (see _run_narrative_gold_set's ABLATION_GOLD_SET_LIMIT
    # docstring) must never be read back as, or overwrite, a full run's
    # cached result under the same cache_key.
    sample_limit = os.environ.get("ABLATION_GOLD_SET_LIMIT")
    sha = git_sha()
    checksum = corpus_checksum(manifest, ANSWER_BOOK)
    key = cache_key(cell, book_key=ANSWER_BOOK, corpus_checksum=checksum or "", git_sha=sha or "")
    cached = None if (force or sample_limit) else load_cache(key)
    if cached is not None:
        _log(f"  [{cell.label}] {ANSWER_BOOK}: cached")
        return [{**cached, "book_key": ANSWER_BOOK, "cache_key": key}]

    try:
        resolved = resolve(_build_ablation_config(cell))
    except AblationAxisNotOwned as exc:
        payload = {
            "status": "blocked",
            "blocked_reason": f"blocked: {exc}",
            "metrics": {"sample_size": 0},
        }
        save_cache(key, payload)
        _log(f"  [{cell.label}] {ANSWER_BOOK}: {payload['status']}")

        return [{**payload, "book_key": ANSWER_BOOK, "cache_key": key}]

    if resolved.inference_mode is not None:
        from api.contracts.enums import InferenceMode

        if resolved.inference_mode == InferenceMode.API:
            from api.config import settings

            if not settings.frontier_model:
                payload = {
                    "status": "blocked",
                    "blocked_reason": BLOCKED_FRONTIER_MODEL,
                    "metrics": {"sample_size": 0},
                }
                save_cache(key, payload)
                _log(f"  [{cell.label}] {ANSWER_BOOK}: {payload['status']}")

                return [{**payload, "book_key": ANSWER_BOOK, "cache_key": key}]

    quality = asyncio.run(
        _run_narrative_gold_set(
            api_base_url,
            ANSWER_BOOK,
            retrieval_mode=resolved.retrieval_mode,
            inference_mode=resolved.inference_mode,
        )
    )
    if not quality.get("gold_available"):
        payload = {
            "status": "blocked",
            "blocked_reason": f"blocked: {quality.get('error') or f'no gold answer set for {ANSWER_BOOK}'}",
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

    if sample_limit:
        cap_note = (
            f"gold set capped to {sample_limit} questions via "
            "ABLATION_GOLD_SET_LIMIT (a CPU-only-vLLM compute-cost stand-in "
            "for this run, not a code limitation) -- see plans/sprint-8/HANDOFF.md"
        )
        if payload["status"] == "measured":
            payload["status"] = "partial"
            payload["blocked_reason"] = f"partial: {cap_note}"
        elif payload["blocked_reason"]:
            payload["blocked_reason"] = f"{payload['blocked_reason']} ({cap_note})"

    if not sample_limit:
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

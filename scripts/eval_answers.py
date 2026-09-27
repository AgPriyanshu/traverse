#!/usr/bin/env python3
"""Drive the S6.14 gold question set through the live API and judge it.

For every question in ``eval/gold/<book>/answers.yaml``: POST ``/api/query``,
collect the SSE stream, and send the result to the frontier judge
(``POST /ops/judge-answer``, ``api/ops/answer_judge.py``). Results are written
to ``eval/gold/<book>/answer_judgements.json`` (resumable: a question already
judged this run is skipped unless ``--rejudge``), and ``GET
/ops/answer-quality`` scores them the same way ``eval/runners/relations.py``
reads a pre-computed ops endpoint.

Like every prior sprint's eval work against a dependency owned by another
agent: a 501 from ``/api/query`` means be2's S6.1-S6.5 has not merged into
this checkout yet. Each such question is recorded as skipped and the script
exits 0 rather than failing a nightly schedule for a dependency it does not
control -- this harness starts asserting for real the moment that work lands,
no code change needed here.

Aggregation completeness (F4.1's "exactly five, not a plausible four") needs
the set of characters the system resolved the answer to, and the frozen SSE
contract has no field for that yet (plans/sprint-6/SCR.md SCR-1). Until that
lands, ``predicted_entities`` is approximated by matching the gold roster's
own canonical names and aliases against the answer text -- noisier than
reading resolved IDs, but the only signal available today.

Usage:
    python3 scripts/eval_answers.py --book-key pride-and-prejudice
    python3 scripts/eval_answers.py --book-key pride-and-prejudice --rejudge
    python3 scripts/eval_answers.py --book-key pride-and-prejudice --summary
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eval.answer_metrics import gold_questions  # noqa: E402
from eval.loaders import load_gold_answers, load_gold_roster  # noqa: E402

_default_api_port = os.environ.get("API_PORT", "8000")
API_BASE_URL = os.environ.get("API_BASE_URL", f"http://localhost:{_default_api_port}")
TREND_FILE = Path(
    os.environ.get("ANSWER_QUALITY_TREND_FILE", "answer-quality-trend.jsonl")
)


def _log(message: str) -> None:
    print(message, flush=True)


def judgements_path(book_key: str) -> Path:
    return REPO_ROOT / "eval" / "gold" / book_key.replace("-", "_") / "answer_judgements.json"


def _get(path: str, *, timeout: float = 30.0) -> tuple[int, Any]:
    url = f"{API_BASE_URL}{path}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload)
        except json.JSONDecodeError:
            return exc.code, {"detail": payload.decode(errors="replace")}


def _post(path: str, payload: dict, *, timeout: float = 90.0) -> tuple[int, str]:
    url = f"{API_BASE_URL}{path}"
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
            return response.status, response.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")


def _post_json(path: str, payload: dict, *, timeout: float = 60.0) -> tuple[int, Any]:
    status_code, raw = _post(path, payload, timeout=timeout)
    try:
        return status_code, json.loads(raw)
    except json.JSONDecodeError:
        return status_code, {"detail": raw}


def parse_sse_events(raw: str) -> list[dict]:
    """Parse a ``text/event-stream`` body into its ``data:`` JSON payloads.

    Frame-agnostic about ``event:``/``id:`` lines -- the wire contract
    (query-path.md) discriminates on each payload's own ``type`` field, never
    the SSE frame shape.
    """
    events = []
    for block in raw.split("\n\n"):
        data_lines = [
            line[len("data:") :].strip()
            for line in block.splitlines()
            if line.startswith("data:")
        ]
        if not data_lines:
            continue
        try:
            events.append(json.loads("\n".join(data_lines)))
        except json.JSONDecodeError:
            continue

    return events


def resolve_project_and_book(book_key: str) -> tuple[str, str]:
    """The newest ingested book whose title slugifies to ``book_key``, and its project."""
    wanted = re.sub(r"[^a-z0-9]+", "-", book_key.lower().replace("_", "-")).strip("-")
    status_code, books = _get("/api/books")
    if status_code != 200:
        raise LookupError(f"GET /api/books returned {status_code}: {books}")
    matches = [
        b
        for b in books
        if re.sub(r"[^a-z0-9]+", "-", b["title"].lower()).strip("-") == wanted
    ]
    if not matches:
        raise LookupError(f"no ingested book matches {book_key!r}")
    matches.sort(key=lambda b: b.get("ingested_at") or "", reverse=True)
    book = matches[0]

    return book["project_id"], book["id"]


def ask(project_id: str, question: str) -> dict:
    """POST /api/query for one question and collect the SSE stream.

    Returns:
        A dict with ``status_code``, and, on a 200: ``answer`` (joined token
        text), ``citations`` (list of the raw ``CitationOut`` dicts, in
        stream order), ``abstained``, ``route`` and ``latency_ms``.
    """
    status_code, raw = _post(
        "/api/query", {"project_id": project_id, "question": question}
    )
    if status_code != 200:
        try:
            detail = json.loads(raw).get("detail", raw)
        except json.JSONDecodeError:
            detail = raw

        return {"status_code": status_code, "detail": detail}

    events = parse_sse_events(raw)
    tokens = []
    citations = []
    abstained = False
    route = None
    latency_ms = None
    errored = None
    for event in events:
        etype = event.get("type")
        if etype == "token":
            tokens.append(event.get("text", ""))
        elif etype == "citation":
            citations.append(event.get("citation", {}))
        elif etype == "route":
            route = event.get("route")
        elif etype == "done":
            abstained = bool(event.get("abstained", False))
            latency_ms = event.get("latency_ms")
        elif etype == "error":
            errored = event.get("message")

    return {
        "status_code": status_code,
        "answer": "".join(tokens) or None,
        "citations": citations,
        "abstained": abstained,
        "route": route,
        "latency_ms": latency_ms,
        "error": errored,
    }


def roster_names(book_key: str) -> list[tuple[str, list[str]]]:
    """(canonical_name, [canonical_name, *aliases]) for every roster character."""
    try:
        roster = load_gold_roster(book_key)
    except FileNotFoundError:
        return []

    return [
        (c["canonical_name"], [c["canonical_name"], *c.get("aliases", [])])
        for c in roster["characters"]
    ]


def extract_predicted_entities(answer: str | None, names: list[tuple[str, list[str]]]) -> list[str]:
    """Which roster characters' names appear in ``answer``.

    A text-matching proxy for the resolved-entity set the aggregation
    exact-match metric wants (plans/sprint-6/SCR.md SCR-1 -- the SSE contract
    has no structured field for it yet). Matches whole words, case-insensitive,
    against every labelled alias, and reports each hit under its canonical name
    once.
    """
    if not answer:
        return []

    found = []
    for canonical, aliases in names:
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias)}\b", answer, re.IGNORECASE):
                found.append(canonical)
                break

    return found


def judge(question, result: dict) -> dict | None:
    """Call the frontier judge for one answered question, or ``None`` on 501."""
    status_code, verdict = _post_json(
        "/api/ops/judge-answer",
        {
            "question_id": question.id,
            "question": question.question,
            "expected_answer": question.expected_answer,
            "expect_abstain": question.expect_abstain,
            "system_answer": result.get("answer"),
            "abstained": result.get("abstained", False),
            "citations": result.get("citations", []),
        },
    )
    if status_code != 200:
        _log(f"  judge-answer HTTP {status_code}: {verdict}")

        return None

    return verdict


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-key", required=True)
    parser.add_argument("--rejudge", action="store_true", help="Re-ask and re-judge every question.")
    parser.add_argument("--limit", type=int, default=None, help="Judge only the first N questions.")
    args = parser.parse_args()

    document = load_gold_answers(args.book_key)
    questions = gold_questions(document)
    if args.limit:
        questions = questions[: args.limit]
    names = roster_names(args.book_key)

    path = judgements_path(args.book_key)
    existing: dict[str, dict] = {}
    if path.exists() and not args.rejudge:
        existing = {
            row["question_id"]: row
            for row in json.loads(path.read_text()).get("answers", [])
        }

    try:
        project_id, _book_id = resolve_project_and_book(args.book_key)
    except LookupError as exc:
        _log(f"SKIP: {exc} -- nothing ingested for {args.book_key!r} yet.")
        project_id = None

    skipped_not_implemented = 0
    judged = 0
    rows: dict[str, dict] = dict(existing)

    for question in questions:
        if question.id in existing and not args.rejudge:
            continue
        if project_id is None:
            continue

        _log(f"[{question.id}] {question.question}")
        start = time.monotonic()
        result = ask(project_id, question.question)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if result["status_code"] == 501:
            _log(f"  SKIP: {result.get('detail')}")
            skipped_not_implemented += 1
            continue
        if result["status_code"] != 200:
            _log(f"  FAIL: HTTP {result['status_code']}: {result.get('detail')}")
            continue

        verdict = judge(question, result)
        predicted_entities = extract_predicted_entities(result.get("answer"), names)
        row = {
            "question_id": question.id,
            "answer": result.get("answer"),
            "abstained": result.get("abstained", False),
            "citations": result.get("citations", []),
            "predicted_entities": predicted_entities,
            "route": result.get("route"),
            "latency_ms": result.get("latency_ms"),
            "client_elapsed_ms": elapsed_ms,
            "judge": verdict,
        }
        rows[question.id] = row
        judged += 1

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"book_key": args.book_key, "answers": list(rows.values())}, indent=2)
            + "\n"
        )

    if judged:
        import datetime

        status_code, quality = _get(f"/api/ops/answer-quality?book_key={args.book_key}")
        if status_code == 200:
            record = {
                "date": datetime.date.today().isoformat(),
                "book": args.book_key,
                "answered": quality.get("answered"),
                "accuracy": (quality.get("accuracy") or {}).get("rate"),
                "citation_precision": (quality.get("citation_precision") or {}).get("rate"),
                "abstention": (quality.get("abstention") or {}).get("rate"),
                "aggregation_exact_match": (quality.get("aggregation_exact_match") or {}).get(
                    "rate"
                ),
            }
            with TREND_FILE.open("a") as handle:
                handle.write(json.dumps(record) + "\n")

    _log(
        f"\n{judged} newly judged, {skipped_not_implemented} skipped (not implemented "
        f"yet), {len(rows)}/{len(questions)} total judged."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())

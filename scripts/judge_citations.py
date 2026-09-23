#!/usr/bin/env python3
"""Terminal tool: human-judge a sample of edge citations (S4.14).

Citation page accuracy is the number the product rests on (F3.2, >= 95%), and
it needs a human. This draws a seeded random sample of evidence items from the
live graph, shows each claim with its quote and page, and takes y/n. Fifty
judgements is about fifteen minutes.

Judgements are written to ``eval/gold/<book>/citation_judgements.json`` keyed
by relation, page and a hash of the quote, so a re-run resumes rather than
re-asking and a changed quote is re-judged. ``GET /ops/relation-quality`` reads
the file.

Usage:
    python3 scripts/judge_citations.py --book-key pride-and-prejudice --n 50
    python3 scripts/judge_citations.py --book-key pride-and-prejudice --summary
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eval.loaders import GOLD_DIR  # noqa: E402
from eval.relation_metrics import citation_page_accuracy  # noqa: E402
from eval.runners.relations import resolve_book_id  # noqa: E402


def judgements_path(book_key: str) -> Path:
    return GOLD_DIR / book_key.replace("-", "_") / "citation_judgements.json"


def item_key(item: dict[str, Any]) -> str:
    digest = hashlib.sha256(item["quote"].encode()).hexdigest()[:12]

    return f"{item['relation_id']}:{item['page_start']}:{digest}"


def _get(base_url: str, path: str) -> Any:
    with urllib.request.urlopen(f"{base_url.rstrip('/')}{path}", timeout=60) as r:  # noqa: S310
        return json.loads(r.read())


def collect_items(base_url: str, book_id: str) -> list[dict[str, Any]]:
    """Every evidence item of every edge in the book's graph."""
    book = next(b for b in _get(base_url, "/api/books") if b["id"] == book_id)
    graph = _get(
        base_url, f"/api/projects/{book['project_id']}/graph?book_id={book_id}"
    )
    names = {n["id"]: n["canonical_name"] for n in graph["nodes"]}
    items = []
    for edge in graph["edges"]:
        rows = _get(base_url, f"/api/relations/{edge['id']}/evidence?limit=200")
        for row in rows:
            items.append(
                {
                    "relation_id": edge["id"],
                    "claim": (
                        f"{names.get(edge['source'], edge['source'])} "
                        f"{edge['predicate']} "
                        f"{names.get(edge['target'], edge['target'])}"
                    ),
                    "page_start": row["page_start"],
                    "page_end": row.get("page_end", row["page_start"]),
                    "quote": row["quote"],
                }
            )

    return items


def draw_sample(items: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    """A deterministic sample, so two people judging the same graph agree on it."""
    ordered = sorted(items, key=item_key)
    rng = random.Random(seed)

    return rng.sample(ordered, min(n, len(ordered)))


def judge(
    sample: list[dict[str, Any]],
    existing: dict[str, dict[str, Any]],
    *,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
    save: Callable[[dict[str, dict[str, Any]]], None] = lambda _: None,
) -> dict[str, dict[str, Any]]:
    """Walk ``sample`` asking y/n/s (skip)/q (quit); saves after every answer."""
    done = dict(existing)
    todo = [i for i in sample if item_key(i) not in done]
    for index, item in enumerate(todo, 1):
        print_fn(
            f"\n[{index}/{len(todo)}] CLAIM: {item['claim']}\n"
            f"  page {item['page_start']}"
            + (f"-{item['page_end']}" if item["page_end"] != item["page_start"] else "")
            + f"\n  QUOTE: {item['quote']}"
        )
        answer = (
            input_fn("Does that page support the claim? [y/n/s/q] ").strip().lower()
        )
        if answer.startswith("q"):
            break
        verdict = (
            True
            if answer.startswith("y")
            else False
            if answer.startswith("n")
            else None
        )
        done[item_key(item)] = {
            **item,
            "supported": verdict,
            "judged_at": datetime.now(UTC).isoformat(),
        }
        save(done)

    return done


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-key", required=True)
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--seed", type=int, default=4)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    path = judgements_path(args.book_key)
    existing: dict[str, dict[str, Any]] = {}
    if path.exists():
        existing = {item_key(j): j for j in json.loads(path.read_text())["judgements"]}

    def save(done: dict[str, dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"book_key": args.book_key, "judgements": list(done.values())}, indent=2
            )
            + "\n"
        )

    if not args.summary:
        book_id = resolve_book_id(args.api_base_url, args.book_key)
        sample = draw_sample(
            collect_items(args.api_base_url, book_id), args.n, args.seed
        )
        existing = judge(sample, existing, save=save)

    score = citation_page_accuracy(existing.values())
    accuracy = "n/a" if score.accuracy is None else f"{score.accuracy:.1%}"
    print(
        f"\ncitation page accuracy: {accuracy} ({score.supported}/{score.judged} "
        f"supported); target 95% on n>=50: {'MET' if score.meets_target else 'not met'}"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())

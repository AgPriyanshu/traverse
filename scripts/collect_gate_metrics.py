#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eval.ablation import metrics_from_answer_quality
from eval.regression_gate import TRACKED_METRICS
from scripts.run_ablation import _get, resolve_book_id


def collect(api_base_url: str, book_key: str) -> dict[str, float | None]:
    metrics: dict[str, float | None] = dict.fromkeys(TRACKED_METRICS)

    book_id = resolve_book_id(api_base_url, book_key)
    if book_id is not None:
        extraction = _get(api_base_url, f"/api/ops/extraction-quality?book_id={book_id}")
        if extraction.get("gold_available"):
            metrics["extraction_f1"] = extraction.get("roster_f1")

        relation = _get(api_base_url, f"/api/ops/relation-quality?book_id={book_id}")
        if relation.get("gold_available"):
            metrics["relation_f1"] = relation.get("f1")

    answer = _get(api_base_url, f"/api/ops/answer-quality?book_key={book_key}")
    if answer.get("gold_available"):
        answer_metrics = metrics_from_answer_quality(answer)
        metrics["answer_accuracy"] = answer_metrics.get("accuracy")
        metrics["citation_precision"] = answer_metrics.get("precision")

    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-key", required=True)
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    metrics = collect(args.api_base_url, args.book_key)
    Path(args.out).write_text(json.dumps(metrics, indent=2, sort_keys=True))
    print(json.dumps(metrics, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

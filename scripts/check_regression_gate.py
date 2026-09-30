#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eval.regression_gate import (
    DEFAULT_THRESHOLD_POINTS,
    TRACKED_METRICS,
    evaluate_gate,
    render_report,
)


def load_metrics(path: str) -> dict[str, float | None]:
    p = Path(path)
    if not p.exists():
        # No stored baseline yet (first run on a fresh branch) -- every
        # metric compares as "no baseline yet", which passes by design
        # rather than failing the very first PR to ever run this gate.
        return dict.fromkeys(TRACKED_METRICS)

    return json.loads(p.read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD_POINTS)
    parser.add_argument("--override-reason", default=None)
    parser.add_argument("--out", default=None, help="write the markdown report here")
    args = parser.parse_args()

    current = load_metrics(args.current)
    baseline = load_metrics(args.baseline)

    result = evaluate_gate(
        current, baseline, threshold=args.threshold, override_reason=args.override_reason
    )
    report = render_report(result)
    print(report)

    if args.out:
        Path(args.out).write_text(report)

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

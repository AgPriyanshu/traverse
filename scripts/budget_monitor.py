#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

_default_api_port = os.environ.get("API_PORT", "8000")
API_BASE_URL = os.environ.get("API_BASE_URL", f"http://localhost:{_default_api_port}")
COMPOSE = os.environ.get("COMPOSE", "docker compose").split()


def _log(message: str) -> None:
    print(message, flush=True)


def fetch_budget_status(api_base_url: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{api_base_url}/ops/budget-status", timeout=10) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        _log(f"budget_monitor: could not reach {api_base_url}/ops/budget-status: {exc}")
        return None


def pause_ingestion() -> None:
    """Stop the worker, not the API — a budget breach degrades, it does not
    take the whole demo offline."""
    _log("budget_monitor: budget breached — stopping celery-worker")
    subprocess.run([*COMPOSE, "stop", "celery-worker"], check=False)


def resume_ingestion() -> None:
    _log("budget_monitor: spend back under budget — starting celery-worker")
    subprocess.run([*COMPOSE, "start", "celery-worker"], check=False)


def check_once(api_base_url: str, *, act: bool) -> int:
    status = fetch_budget_status(api_base_url)
    if status is None:
        return 1

    pct = status["pct_used"] * 100
    _log(
        f"budget_monitor: ${status['spent_usd']:.2f} / ${status['budget_usd']:.2f} "
        f"({pct:.1f}%) warning={status['warning']} breached={status['breached']}"
    )

    if not act:
        return 1 if status["breached"] else 0

    if status["breached"]:
        pause_ingestion()
        return 1

    resume_ingestion()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default=API_BASE_URL)
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help="Poll forever at this interval in seconds. Omit for a single check.",
    )
    parser.add_argument(
        "--no-act",
        action="store_true",
        help="Report only; never stop/start celery-worker (dry run / CI check).",
    )
    args = parser.parse_args()

    if args.interval is None:
        return check_once(args.api_base_url, act=not args.no_act)

    while True:
        check_once(args.api_base_url, act=not args.no_act)
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())

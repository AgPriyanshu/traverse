#!/usr/bin/env python3
"""Ingest one corpus book through the running stack: `make ingest BOOK=<key>`.

Creates the demo project if it does not exist (``POST /projects`` is S5.9, so
this goes to Postgres like the other scripts), uploads
``corpus/downloads/<key>.pdf`` through the API and polls ``/status`` until the
book is terminal. A book already ``ready`` in the project is reused, so the
sprint demo script can be re-run without stacking duplicates.

Usage:
    python3 scripts/ingest_book.py pride_and_prejudice
    python3 scripts/ingest_book.py wuthering-heights --project-slug demo --force
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import test_integration_ingestion as gate  # noqa: E402

POLL_TIMEOUT_S = 40 * 60


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def ensure_project(project_slug: str) -> str:
    # The native Enum column stores the member NAME, not its value.
    gate._psql(
        "INSERT INTO project (id, name, slug, kind, roster_version) VALUES "
        f"(gen_random_uuid(), 'Demo', '{project_slug}', 'STANDALONE', 0) "
        "ON CONFLICT (slug) DO NOTHING;"
    )

    return gate._psql(f"SELECT id FROM project WHERE slug = '{project_slug}';")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book", help="corpus key, hyphens or underscores")
    parser.add_argument("--project-slug", default="demo")
    parser.add_argument("--force", action="store_true", help="upload even if ready")
    args = parser.parse_args()

    key = slug(args.book)
    pdf_path = REPO_ROOT / "corpus" / "downloads" / f"{key}.pdf"
    if not pdf_path.exists():
        print(f"FAIL: {pdf_path.relative_to(REPO_ROOT)} missing -- run `make seed`.")

        return 1

    project_id = ensure_project(args.project_slug)
    status_code, books = gate._request("GET", f"/api/books?project_id={project_id}")
    if status_code != 200:
        print(f"FAIL: GET /api/books returned {status_code}: {books}")

        return 1
    same_title = [b for b in books if slug(b["title"]) == key]
    ready = [b for b in same_title if b["status"] == "ready"]
    if ready and not args.force:
        print(f"already ingested: book_id={ready[0]['id']} (use --force to re-upload)")

        return 0

    order = max((b.get("series_order") or 0 for b in books), default=0) + 1
    body, boundary = gate._multipart_body(
        "file", pdf_path.name, pdf_path.read_bytes(), "application/pdf"
    )
    status_code, created = gate._request(
        "POST",
        f"/api/projects/{project_id}/books?series_order={order}",
        body=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    if status_code != 202:
        print(f"FAIL: upload returned {status_code}: {created}")

        return 1
    book_id = created["id"]
    print(f"uploaded: book_id={book_id}; polling status")
    before = gate.fetch_vllm_prefix_cache_counters()
    final = gate.poll_status(book_id, timeout_s=POLL_TIMEOUT_S)
    after = gate.fetch_vllm_prefix_cache_counters()
    print(f"{key}: {final['status']}  book_id={book_id}")
    rate = gate.prefix_cache_hit_rate_between(before, after)
    if rate is not None:
        print(f"  prefix-cache hit rate (this run, scoped): {rate:.1%}")
    if final["status"] != "ready":
        for stage in final.get("stages", []):
            if stage.get("state") == "failed":
                print(f"  {stage['stage']}: {stage.get('error')}")

        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

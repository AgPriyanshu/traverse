#!/usr/bin/env python3
"""Create the S5.13 series projects and queue their books: `make seed-series`.

Builds on `scripts/seed_corpus.py`'s ``SERIES_CORPUS`` (Anne of Green Gables,
Sherlock Holmes) the same way `scripts/ingest_book.py` builds on the
standalone five: paginate first (idempotent, checksum-verified), then create
each project (``kind=SERIES``, straight to Postgres like `ingest_book.py` --
``POST /projects`` is still S5.9) and upload its books through the real API
in ``series_order``, one at a time.

Sequential, not concurrent: this is the corpus-seeding path, not the
concurrency stress test (`scripts/ingest_series.py`, S5.15) -- it waits for
each book to reach a terminal status before uploading the next, which is
always safe regardless of whether the per-project reconcile lock (see
plans/sprint-5/SCR.md SCR-1) has landed yet.

Usage:
    python3 scripts/seed_series.py
    python3 scripts/seed_series.py --only anne-of-green-gables
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import test_integration_ingestion as gate  # noqa: E402
from seed_corpus import CorpusBook, load_manifest, process_book  # noqa: E402
from seed_corpus import series_books, write_licenses_md  # noqa: E402

SERIES_KEYS = ("anne-of-green-gables", "sherlock-holmes")
POLL_TIMEOUT_S = 40 * 60


def ensure_project(project_slug: str, name: str) -> str:
    """Create the series project directly in Postgres, idempotently.

    ``POST /projects`` is still S5.9 (fe1), so this goes straight to the
    database like `scripts/ingest_book.py`'s ``ensure_project`` -- the same
    reasoning, just with ``kind='SERIES'`` instead of ``'STANDALONE'``.
    """
    gate._psql(
        "INSERT INTO project (id, name, slug, kind, roster_version) VALUES "
        f"(gen_random_uuid(), '{name}', '{project_slug}', 'SERIES', 0) "
        "ON CONFLICT (slug) DO NOTHING;"
    )

    return gate._psql(f"SELECT id FROM project WHERE slug = '{project_slug}';")


def upload_series_book(project_id: str, book: CorpusBook) -> str:
    """Upload one already-paginated series book; return its book_id.

    Idempotent like `scripts/ingest_book.py`: a book already at this
    project's ``series_order`` and ``ready`` is reused rather than re-queued,
    so re-running `make seed-series` never stacks duplicate uploads.
    """
    pdf_path = REPO_ROOT / "corpus" / "downloads" / f"{book.key}.pdf"
    status_code, books = gate._request("GET", f"/api/books?project_id={project_id}")
    if status_code != 200:
        raise RuntimeError(f"GET /api/books returned {status_code}: {books}")

    existing = [b for b in books if b.get("series_order") == book.series_order]
    ready = [b for b in existing if b["status"] == "ready"]
    if ready:
        print(f"  have    {book.key} (book_id={ready[0]['id']}, already ready)")

        return ready[0]["id"]

    body, boundary = gate._multipart_body(
        "file", pdf_path.name, pdf_path.read_bytes(), "application/pdf"
    )
    status_code, created = gate._request(
        "POST",
        f"/api/projects/{project_id}/books?series_order={book.series_order}",
        body=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    if status_code not in (200, 202):
        raise RuntimeError(f"upload of {book.key} returned {status_code}: {created}")

    book_id = created["id"]
    print(f"  queued  {book.key} -> book_id={book_id}, polling status")
    final = gate.poll_status(book_id, timeout_s=POLL_TIMEOUT_S)
    print(f"  {book.key}: {final['status']}")
    if final["status"] != "ready":
        for stage in final.get("stages", []):
            if stage.get("state") == "failed":
                print(f"    {stage['stage']}: {stage.get('error')}")

    return book_id


def seed_one_series(series_key: str) -> None:
    books = series_books(series_key)
    if not books:
        raise SystemExit(f"no series books registered for {series_key!r}")

    print(f"==> {books[0].project_name} ({series_key})")
    for book in books:
        process_book(book, force=False)  # idempotent, checksum-verified.

    project_id = ensure_project(series_key, books[0].project_name)
    print(f"    project_id={project_id}")
    for book in books:
        upload_series_book(project_id, book)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="Comma-separated series keys (default: both).")
    args = parser.parse_args()

    wanted = set(args.only.split(",")) if args.only else set(SERIES_KEYS)
    unknown = wanted - set(SERIES_KEYS)
    if unknown:
        raise SystemExit(f"unknown series key(s) {sorted(unknown)}; know {SERIES_KEYS}")

    for series_key in SERIES_KEYS:
        if series_key in wanted:
            seed_one_series(series_key)

    write_licenses_md(load_manifest())
    print("\nmake seed-series done.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

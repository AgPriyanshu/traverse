#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import test_integration_ingestion as gate  # noqa: E402
from seed_corpus import CorpusBook, process_book, series_books  # noqa: E402

POLL_TIMEOUT_S = 40 * 60


def ensure_project(project_slug: str, name: str) -> str:
    gate._psql(
        "INSERT INTO project (id, name, slug, kind, roster_version) VALUES "
        f"(gen_random_uuid(), '{name}', '{project_slug}', 'SERIES', 0) "
        "ON CONFLICT (slug) DO NOTHING;"
    )

    return gate._psql(f"SELECT id FROM project WHERE slug = '{project_slug}';")


@dataclass
class BookReport:
    key: str
    series_order: int
    book_id: str | None = None
    status: str = "skipped"
    wall_clock_s: float = 0.0
    pass1_cost_usd: float | None = None
    pass2_cost_usd: float | None = None
    prefix_cache_hit_rate: float | None = None
    character_count: int | None = None
    error: str | None = None


@dataclass
class SeriesReport:
    series_key: str
    project_id: str
    project_slug: str
    concurrent: bool
    books: list[BookReport] = field(default_factory=list)

    @property
    def total_wall_clock_s(self) -> float:
        return sum(b.wall_clock_s for b in self.books)

    @property
    def total_cost_usd(self) -> float:
        return sum(
            (b.pass1_cost_usd or 0.0) + (b.pass2_cost_usd or 0.0) for b in self.books
        )


def _upload(project_id: str, book: CorpusBook) -> str:
    """POST one book's PDF; return its book_id. Idempotent on series_order."""
    pdf_path = REPO_ROOT / "corpus" / "downloads" / f"{book.key}.pdf"
    status_code, books = gate._request("GET", f"/api/books?project_id={project_id}")
    if status_code != 200:
        raise RuntimeError(f"GET /api/books returned {status_code}: {books}")
    existing = [b for b in books if b.get("series_order") == book.series_order]
    ready = [b for b in existing if b["status"] == "ready"]
    if ready:
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

    return created["id"]


def _project_character_count(api_base_url: str, project_id: str) -> int | None:
    status_code, project = gate._request("GET", f"/api/projects/{project_id}")
    if status_code != 200:
        return None

    return project.get("character_count")


def _cost_report(book_id: str) -> tuple[float | None, float | None]:
    """Best-effort local-amortised USD for pass 1 and pass 2 of one book."""
    status_code, extraction = gate._request(
        "GET", f"/api/ops/extraction-cost?book_id={book_id}"
    )
    pass1 = extraction.get("total_cost_usd_local") if status_code == 200 else None
    status_code, relation = gate._request(
        "GET", f"/api/ops/relation-cost?book_id={book_id}"
    )
    pass2 = relation.get("total_cost_usd_local") if status_code == 200 else None

    return pass1, pass2


def ingest_one_book(project_id: str, book: CorpusBook) -> BookReport:
    report = BookReport(key=book.key, series_order=book.series_order or 0)
    started = time.monotonic()
    try:
        book_id = _upload(project_id, book)
        report.book_id = book_id
        final = gate.poll_status(book_id, timeout_s=POLL_TIMEOUT_S)
        report.status = final["status"]
        report.pass1_cost_usd, report.pass2_cost_usd = _cost_report(book_id)
        report.character_count = _project_character_count(gate.API_BASE_URL, project_id)
    except (RuntimeError, TimeoutError) as exc:
        report.status = "error"
        report.error = str(exc)
    report.wall_clock_s = time.monotonic() - started

    return report


def ingest_series(
    series_key: str,
    *,
    project_slug: str | None = None,
    reverse: bool = False,
    limit_books: int | None = None,
    concurrent: bool = False,
) -> SeriesReport:
    books = series_books(series_key)
    if not books:
        raise SystemExit(f"no series books registered for {series_key!r}")
    if limit_books is not None:
        books = books[:limit_books]

    # `series_order` stays each book's true narrative position -- only the
    # UPLOAD sequence reverses. This is what "reverse-order upload produces
    # an identical graph" (Sprint 5 DoD) actually tests: the same facts,
    # discovered in the opposite order.
    upload_order = list(reversed(books)) if reverse else books

    for book in books:
        process_book(book, force=False)

    slug = project_slug or series_key
    project_id = ensure_project(slug, upload_order[0].project_name or series_key)

    report = SeriesReport(
        series_key=series_key, project_id=project_id, project_slug=slug,
        concurrent=concurrent,
    )

    if concurrent:
        # A deliberate race -- see the module docstring and SCR-2. Every
        # upload fires immediately; nothing here waits for a prior book's
        # reconcile stage before starting the next.
        with ThreadPoolExecutor(max_workers=len(upload_order)) as pool:
            report.books = list(
                pool.map(lambda b: ingest_one_book(project_id, b), upload_order)
            )
    else:
        for book in upload_order:
            report.books.append(ingest_one_book(project_id, book))

    report.books.sort(key=lambda b: b.series_order)

    return report


def roster_growth_lines(report: SeriesReport) -> list[str]:
    """The roster-growth curve: does pass-2 cost grow faster than the roster?

    A ratio-of-ratios consistently above 1 across consecutive books is the
    superlinear-growth finding devops-1.md calls out as belonging in the
    writeup, not buried in a retro -- printed here as the raw numbers a human
    can judge, not as a single verdict.
    """
    lines = [
        "| Book | Roster size | Pass-2 cost (USD) | Cost/roster ratio vs prior book |",
        "| --- | --- | --- | --- |",
    ]
    prior_cost: float | None = None
    prior_roster: int | None = None
    ratios: list[float] = []
    for book in sorted(report.books, key=lambda b: b.series_order):
        ratio_cell = "-"
        if (
            prior_cost
            and prior_roster
            and book.pass2_cost_usd is not None
            and book.character_count is not None
            and prior_cost > 0
            and prior_roster > 0
        ):
            cost_ratio = book.pass2_cost_usd / prior_cost
            roster_ratio = book.character_count / prior_roster
            if roster_ratio > 0:
                ratio = cost_ratio / roster_ratio
                ratios.append(ratio)
                ratio_cell = f"{ratio:.2f}"
        lines.append(
            f"| {book.key} | {book.character_count if book.character_count is not None else '-'} "
            f"| {f'{book.pass2_cost_usd:.4f}' if book.pass2_cost_usd is not None else '-'} "
            f"| {ratio_cell} |"
        )
        if book.pass2_cost_usd is not None:
            prior_cost = book.pass2_cost_usd
        if book.character_count is not None:
            prior_roster = book.character_count

    if ratios:
        average = sum(ratios) / len(ratios)
        verdict = (
            "pass-2 cost appears to grow FASTER than the roster (superlinear) "
            "-- a real architectural finding, not noise"
            if average > 1.15
            else "pass-2 cost tracks roster growth roughly linearly"
        )
        lines += ["", f"Average cost/roster ratio: {average:.2f} -- {verdict}."]

    return lines


def render_report(report: SeriesReport) -> str:
    lines = [
        f"### Series ingestion — {report.series_key}",
        "",
        f"Project `{report.project_id}` (slug `{report.project_slug}`), "
        f"{'concurrent (stress test, see SCR-2)' if report.concurrent else 'sequential'}, "
        f"{len(report.books)} books.",
        "",
        "| Book | Order | Status | Wall clock (s) | Pass-1 $ | Pass-2 $ | Prefix-cache hit rate |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for book in report.books:
        lines.append(
            f"| {book.key} | {book.series_order} | {book.status} | "
            f"{book.wall_clock_s:.1f} | "
            f"{f'{book.pass1_cost_usd:.4f}' if book.pass1_cost_usd is not None else '-'} | "
            f"{f'{book.pass2_cost_usd:.4f}' if book.pass2_cost_usd is not None else '-'} | "
            f"{f'{book.prefix_cache_hit_rate:.1%}' if book.prefix_cache_hit_rate is not None else '-'} |"
        )
    lines += [
        "",
        f"**Totals:** {report.total_wall_clock_s:.1f}s wall clock, "
        f"${report.total_cost_usd:.4f} local-amortised.",
        "",
        "### Roster-growth cost curve",
        "",
        *roster_growth_lines(report),
    ]
    errors = [b for b in report.books if b.error]
    if errors:
        lines += ["", "**Errors:**"]
        lines += [f"- {b.key}: {b.error}" for b in errors]

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("series_key", help="e.g. anne-of-green-gables, sherlock-holmes")
    parser.add_argument("--api-base-url", default=gate.API_BASE_URL)
    parser.add_argument("--project-slug")
    parser.add_argument(
        "--reverse", action="store_true", help="Upload in reverse series order."
    )
    parser.add_argument("--limit-books", type=int)
    parser.add_argument(
        "--concurrent",
        action="store_true",
        help="Fire every book's upload immediately (a deliberate race, see SCR-2).",
    )
    parser.add_argument("--save-json")
    parser.add_argument("--out", help="Markdown destination; stdout if omitted.")
    args = parser.parse_args()

    gate.API_BASE_URL = args.api_base_url
    report = ingest_series(
        args.series_key,
        project_slug=args.project_slug,
        reverse=args.reverse,
        limit_books=args.limit_books,
        concurrent=args.concurrent,
    )
    markdown = render_report(report)
    if args.out:
        Path(args.out).write_text(markdown)
    else:
        print(markdown)
    if args.save_json:
        Path(args.save_json).write_text(
            json.dumps(
                {
                    "series_key": report.series_key,
                    "project_id": report.project_id,
                    "project_slug": report.project_slug,
                    "concurrent": report.concurrent,
                    "books": [vars(b) for b in report.books],
                },
                indent=2,
            )
        )

    failed = [b for b in report.books if b.status not in ("ready",)]

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

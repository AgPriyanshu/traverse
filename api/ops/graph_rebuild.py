"""The Neo4j rebuild-from-Postgres drill (S4.15).

PRD section 5.5 claims a corrupted graph is a re-upsert, never data loss. This
proves it for one book: snapshot the projection, ``graph.reset`` the book,
re-run ``graph.upsert`` from Postgres, and require the node count, edge count
and a content checksum to match the pre-wipe state.

Run it with ``make graph-rebuild BOOK=<key>``, or import ``run_drill`` from a
test. ``graph.upsert`` is invoked through its frozen Celery name, the same way
the ingestion chain does, so this needs no import of be2's package.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from uuid import UUID

from sqlmodel import select

from ..contracts.enums import StageName

REBUILD_BUDGET_S = 120.0
UPSERT_TIMEOUT_S = 600.0

_NODES = """
MATCH (c:Character {project_id: $project_id})
RETURN c.id AS id, c.canonical_name AS name, c.importance_tier AS tier,
       c.mention_count AS mentions, c.first_book_order AS first_order,
       c.first_chapter AS first_chapter,
       coalesce(c.appears_in_books, []) AS books
"""

_EDGES = """
MATCH (a:Character {project_id: $project_id})-[r:RELATED]->(b:Character)
RETURN r.id AS id, a.id AS subject, b.id AS object, r.predicate AS predicate,
       r.family AS family, r.status AS status, r.assertion_type AS assertion,
       r.hearsay AS hearsay, r.evidence_count AS evidence_count,
       round(coalesce(r.confidence, 0.0) * 1000000) AS confidence,
       coalesce(r.page_refs, []) AS page_refs,
       coalesce(r.book_refs, []) AS book_refs,
       r.first_book_order AS first_order, r.first_chapter AS first_chapter,
       r.last_book_order AS last_order, r.last_chapter AS last_chapter
"""

_APPEARANCES = """
MATCH (c:Character {project_id: $project_id})-[a:APPEARS_IN]->(b:Book)
RETURN c.id AS character, b.id AS book, a.first_page AS first_page,
       a.mention_count AS mentions, a.tier AS tier
"""


@dataclass(frozen=True)
class GraphSnapshot:
    nodes: int
    edges: int
    appearances: int
    evidence_free_edges: int
    checksum: str


def _sortable(value: object) -> object:
    if isinstance(value, list):
        return sorted(value, key=str)

    return value


def _digest(*groups: list[dict]) -> str:
    """Order-independent content hash: rows and list properties are sorted."""
    hasher = hashlib.sha256()
    for rows in groups:
        lines = sorted(
            json.dumps({k: _sortable(v) for k, v in row.items()}, sort_keys=True)
            for row in rows
        )
        hasher.update(("\n".join(lines) + "\x1e").encode())

    return hasher.hexdigest()


async def snapshot(project_id: UUID | str) -> GraphSnapshot:
    """Count and checksum one project's projection in Neo4j.

    ``stale`` is deliberately not hashed: it marks an edge trimmed by a reset
    and is cleared by the upsert, so it is a property of the wipe, not of the
    projection being compared.
    """
    from ..graph import client

    params = {"project_id": str(project_id)}
    nodes = [dict(r) for r in (await client.execute(_NODES, **params)).records]
    edges = [dict(r) for r in (await client.execute(_EDGES, **params)).records]
    appearances = [
        dict(r) for r in (await client.execute(_APPEARANCES, **params)).records
    ]
    evidence_free = sum(1 for e in edges if not e["evidence_count"] or not e["page_refs"])

    return GraphSnapshot(
        nodes=len(nodes),
        edges=len(edges),
        appearances=len(appearances),
        evidence_free_edges=evidence_free,
        checksum=_digest(nodes, edges, appearances),
    )


def _run_upsert(book_id: str, timeout_s: float) -> None:
    from ..tasks import celery_app

    result = celery_app.signature(
        StageName.UPSERT_GRAPH.value, args=(book_id,), immutable=True
    ).apply_async()
    result.get(timeout=timeout_s, propagate=True)


@dataclass(frozen=True)
class DrillReport:
    book_id: str
    project_id: str
    before: GraphSnapshot
    wiped: GraphSnapshot
    after: GraphSnapshot
    elapsed_s: float
    identical: bool
    within_budget: bool
    wipe_effective: bool

    @property
    def passed(self) -> bool:
        return (
            self.identical
            and self.within_budget
            and self.wipe_effective
            and self.after.evidence_free_edges == 0
        )


async def run_drill(
    book_id: UUID | str,
    *,
    budget_s: float = REBUILD_BUDGET_S,
    upsert_timeout_s: float = UPSERT_TIMEOUT_S,
) -> DrillReport:
    """Wipe one book's projection, rebuild it from Postgres, compare.

    Args:
        book_id: The book to rebuild.
        budget_s: Wall-clock limit for reset plus rebuild (the S4.15 acceptance
            is two minutes for a 900-edge graph).
        upsert_timeout_s: Hard stop on the upsert task itself.

    Returns:
        Snapshots before, after the wipe and after the rebuild, and verdicts.
        The drill refuses to pass on an empty graph: an identical projection
        of nothing proves nothing.
    """
    from ..db.engine import db_session
    from ..db.models import Book
    from ..graph import projection

    async with db_session() as session:
        book = await session.get(Book, UUID(str(book_id)))
    if book is None:
        raise LookupError(f"book {book_id} not found")
    project_id = str(book.project_id)

    before = await snapshot(project_id)

    started = time.monotonic()
    await projection.reset(book_id, project_id=project_id)
    wiped = await snapshot(project_id)
    await asyncio.to_thread(_run_upsert, str(book_id), upsert_timeout_s)
    elapsed = time.monotonic() - started
    after = await snapshot(project_id)

    return DrillReport(
        book_id=str(book_id),
        project_id=project_id,
        before=before,
        wiped=wiped,
        after=after,
        elapsed_s=elapsed,
        identical=before.checksum == after.checksum
        and (before.nodes, before.edges) == (after.nodes, after.edges),
        within_budget=elapsed <= budget_s,
        wipe_effective=before.nodes > 0
        and (wiped.nodes, wiped.edges) != (before.nodes, before.edges),
    )


async def _resolve_book(book_id: str | None, book_key: str | None) -> str:
    if book_id:
        return book_id

    from ..db.engine import db_session
    from ..db.models import Book

    wanted = re.sub(r"[^a-z0-9]+", "-", (book_key or "").lower().replace("_", "-"))
    async with db_session() as session:
        rows = (
            (await session.execute(select(Book).order_by(Book.created_at.desc())))  # type: ignore[attr-defined]
            .scalars()
            .all()
        )
    for book in rows:
        if re.sub(r"[^a-z0-9]+", "-", book.title.lower()).strip("-") == wanted:
            return str(book.id)
    raise LookupError(f"no ingested book matches {book_key!r}")


def _render(report: DrillReport) -> str:
    def row(name: str, snap: GraphSnapshot) -> str:
        return (
            f"  {name:<8} nodes={snap.nodes:<5} edges={snap.edges:<5} "
            f"appearances={snap.appearances:<5} sha256={snap.checksum[:16]}"
        )

    verdict = "PASS" if report.passed else "FAIL"
    lines = [
        f"graph rebuild drill: {verdict}  book={report.book_id}",
        row("before", report.before),
        row("wiped", report.wiped),
        row("after", report.after),
        f"  elapsed {report.elapsed_s:.1f}s (budget {REBUILD_BUDGET_S:.0f}s)",
    ]
    if not report.wipe_effective:
        lines.append("  the wipe changed nothing (empty graph?): the drill proved nothing")
    if not report.identical:
        lines.append("  projection differs from the pre-wipe state")
    if report.after.evidence_free_edges:
        lines.append(f"  {report.after.evidence_free_edges} evidence-free edges")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id")
    parser.add_argument("--book-key", help="e.g. pride-and-prejudice")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not (args.book_id or args.book_key):
        parser.error("give --book-id or --book-key")

    async def go() -> DrillReport:
        book_id = await _resolve_book(args.book_id, args.book_key)

        return await run_drill(book_id)

    report = asyncio.run(go())
    print(json.dumps(asdict(report), indent=2) if args.json else _render(report))

    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())

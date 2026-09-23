import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import String, cast, update
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..db.models.relation_model import Relation
from . import ontology, repository
from .client import session as neo_session

logger = logging.getLogger(__name__)


class EvidenceRequiredError(ValueError):
    """Raised when an edge with no evidence is offered to the projection.

    An unevidenced edge is a hallucination with a UI (PRD F3.2). This is a
    guard that raises, not a filter that skips: a skipped edge would hide the
    bug that produced it.
    """


class ProjectionMismatchError(RuntimeError):
    """Raised when the projected edge count differs from what Postgres holds."""


_UPSERT_BOOKS = """
UNWIND $rows AS row
MERGE (b:Book {id: row.id})
SET b.project_id = row.project_id,
    b.series_order = row.series_order,
    b.title = row.title
"""

_UPSERT_CHARACTERS = """
UNWIND $rows AS row
MERGE (c:Character {id: row.id})
SET c.project_id = row.project_id,
    c.canonical_name = row.canonical_name,
    c.importance_tier = row.importance_tier,
    c.mention_count = row.mention_count,
    c.first_book_order = row.first_book_order,
    c.first_chapter = row.first_chapter,
    c.appears_in_books = row.appears_in_books
"""

_UPSERT_APPEARANCES = """
UNWIND $rows AS row
MATCH (c:Character {id: row.character_id})
MATCH (b:Book {id: row.book_id})
MERGE (c)-[a:APPEARS_IN {book_id: row.book_id}]->(b)
"""

_DELETE_STALE_APPEARANCES = """
MATCH (c:Character {project_id: $project_id})-[a:APPEARS_IN]->(:Book)
WHERE NOT (c.id + '|' + a.book_id) IN $keys
DELETE a
"""

_DELETE_STALE_EDGES = """
MATCH (:Character)-[r:RELATED {project_id: $project_id}]->(:Character)
WHERE NOT r.key IN $keys
DELETE r
"""

_DELETE_STALE_CHARACTERS = """
MATCH (c:Character {project_id: $project_id})
WHERE NOT c.id IN $ids
DETACH DELETE c
"""

_DELETE_STALE_BOOKS = """
MATCH (b:Book {project_id: $project_id})
WHERE NOT b.id IN $ids
DETACH DELETE b
"""

_UPSERT_EDGES = """
UNWIND $rows AS row
MATCH (s:Character {id: row.source})
MATCH (t:Character {id: row.target})
MERGE (s)-[r:RELATED {key: row.key}]->(t)
SET r += row.props
"""

_COUNT_EDGES = """
MATCH (:Character)-[r:RELATED {project_id: $project_id}]->(:Character)
RETURN count(r) AS total
"""


def _page_refs(evidence: list[Any]) -> list[str]:
    refs: set[tuple[int, int]] = set()
    for item in evidence:
        for page in range(item.page_start, item.page_end + 1):
            refs.add((item.book_order, page))

    return [f"{order}:{page}" for order, page in sorted(refs)]


def build_edge_rows(
    project_id: UUID, relations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Turn Postgres relations into Neo4j edge rows, inverses included.

    An inverse edge is materialised so traversal never depends on which
    direction extraction happened to write: ``parent_of(A, B)`` also exists as
    ``child_of(B, A)``, and a symmetric edge exists in both directions.

    Raises:
        EvidenceRequiredError: If any relation has no evidence rows. Counted
            from the rows themselves, not the ``evidence_count`` column, which
            could be stale.
    """
    rows: list[dict[str, Any]] = []
    for entry in relations:
        relation: Relation = entry["relation"]
        evidence = entry["evidence"]
        if not evidence:
            raise EvidenceRequiredError(
                f"relation {relation.id} ({relation.predicate}) has no evidence; "
                "refusing to project an unevidenced edge"
            )

        props = {
            "id": str(relation.id),
            "project_id": str(project_id),
            "family": relation.family.value,
            "confidence": relation.confidence,
            "status": relation.status.value,
            "assertion_type": relation.assertion_type.value,
            "hearsay": relation.hearsay,
            "evidence_count": len(evidence),
            "page_refs": _page_refs(evidence),
            "book_refs": sorted({str(item.book_id) for item in evidence}),
            "first_book_order": relation.first_book_order,
            "first_chapter": relation.first_chapter,
            "last_book_order": relation.last_book_order,
            "last_chapter": relation.last_chapter,
        }
        subject = str(relation.subject_character_id)
        target = str(relation.object_character_id)
        rows.append(
            {
                "key": f"{relation.id}:fwd",
                "source": subject,
                "target": target,
                "props": {
                    **props,
                    "key": f"{relation.id}:fwd",
                    "predicate": relation.predicate,
                    "inverse": False,
                },
            }
        )

        spec = ontology.spec_of(relation.predicate)
        if spec.inverse is not None:
            rows.append(
                {
                    "key": f"{relation.id}:inv",
                    "source": target,
                    "target": subject,
                    "props": {
                        **props,
                        "key": f"{relation.id}:inv",
                        "predicate": spec.inverse,
                        "inverse": True,
                    },
                }
            )

    return rows


async def upsert_project(session: SQLModelAsyncSession, project_id: UUID) -> dict:
    """Project a project's Postgres state into Neo4j, atomically.

    Idempotent: MERGE on stable keys, then anything Postgres no longer holds is
    deleted, so running it twice, or after a merge, converges on the same graph.

    Args:
        session: An open Postgres session.
        project_id: The project to project.

    Returns:
        Counts of what was projected.

    Raises:
        EvidenceRequiredError: If any relation has no evidence. Raised before
            Neo4j is touched.
        ProjectionMismatchError: If Neo4j ends up with a different number of
            edges than Postgres implies, e.g. an edge endpoint was missing.
    """
    data = await repository.load_projection_rows(session, project_id)
    edges = build_edge_rows(project_id, data["relations"])
    pid = str(project_id)

    appearance_keys = [
        f"{a['character_id']}|{a['book_id']}" for a in data["appearances"]
    ]

    async def work(tx) -> int:
        await tx.run(_UPSERT_BOOKS, rows=data["books"])
        await tx.run(_UPSERT_CHARACTERS, rows=data["characters"])
        await tx.run(_UPSERT_APPEARANCES, rows=data["appearances"])
        await tx.run(_DELETE_STALE_APPEARANCES, project_id=pid, keys=appearance_keys)
        await tx.run(_UPSERT_EDGES, rows=edges)
        await tx.run(
            _DELETE_STALE_EDGES, project_id=pid, keys=[e["key"] for e in edges]
        )
        await tx.run(
            _DELETE_STALE_CHARACTERS,
            project_id=pid,
            ids=[c["id"] for c in data["characters"]],
        )
        await tx.run(
            _DELETE_STALE_BOOKS, project_id=pid, ids=[b["id"] for b in data["books"]]
        )
        cursor = await tx.run(_COUNT_EDGES, project_id=pid)
        record = await cursor.single()

        return int(record["total"])

    async with neo_session() as neo:
        total = await neo.execute_write(work)

    if total != len(edges):
        raise ProjectionMismatchError(
            f"project {project_id}: expected {len(edges)} edges in Neo4j, found "
            f"{total}; an edge endpoint is probably missing from the roster"
        )

    await session.execute(
        update(Relation)
        .where(Relation.project_id == project_id)
        .values(graph_edge_id=cast(Relation.id, String))
    )
    await session.commit()

    counts = {
        "books": len(data["books"]),
        "characters": len(data["characters"]),
        "relations": len(data["relations"]),
        "edges": len(edges),
    }
    logger.info("project %s projected: %s", project_id, counts)

    return counts


async def snapshot(project_id: UUID | str) -> str:
    """Return a canonical JSON dump of a project's projection.

    Two calls around a wipe-and-rebuild must be byte-identical; that equality is
    the rebuild drill's acceptance test.
    """
    pid = str(project_id)
    async with neo_session() as neo:
        nodes = await (
            await neo.run(
                "MATCH (c:Character {project_id: $p}) RETURN properties(c) AS n "
                "ORDER BY c.id",
                p=pid,
            )
        ).data()
        edges = await (
            await neo.run(
                "MATCH (:Character)-[r:RELATED {project_id: $p}]->(:Character) "
                "RETURN properties(r) AS r ORDER BY r.key",
                p=pid,
            )
        ).data()

    dump = json.dumps({"nodes": nodes, "edges": edges}, sort_keys=True)

    return dump

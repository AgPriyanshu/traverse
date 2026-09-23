import logging
from uuid import UUID

from neo4j.exceptions import Neo4jError, ServiceUnavailable
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import (
    GraphEdgeOut,
    GraphNodeOut,
    GraphOut,
    GraphPathOut,
    PageRefOut,
)
from ..contracts.enums import ImportanceTier, RelationFamily
from . import repository
from .client import session as neo_session

logger = logging.getLogger(__name__)

MAX_HOPS = 4
MAX_DEPTH = 2

# A position is visible when it is at or before the reader's. With no chapter
# limit, only positions with no chapter at all are visible inside that book,
# matching ``repository._within_reading_position``.
_VISIBLE = """(
  $lbo IS NULL OR {a}.first_book_order IS NULL OR {a}.first_book_order < $lbo
  OR ({a}.first_book_order = $lbo
      AND ({a}.first_chapter IS NULL
           OR ($lch IS NOT NULL AND {a}.first_chapter <= $lch)))
)"""

_NODES = f"""
MATCH (c:Character {{project_id: $pid}})
WHERE {_VISIBLE.format(a="c")}
RETURN properties(c) AS n
ORDER BY c.id
"""

_EDGES = f"""
MATCH (s:Character)-[r:RELATED {{project_id: $pid, inverse: false}}]->(t:Character)
WHERE ($families IS NULL OR r.family IN $families)
  AND r.confidence >= $min_confidence
  AND ($book IS NULL OR $book IN r.book_refs)
  AND {_VISIBLE.format(a="r")}
RETURN properties(r) AS r, s.id AS source, t.id AS target
ORDER BY r.confidence DESC, r.id
LIMIT $limit
"""


def _node_out(props: dict) -> GraphNodeOut:
    node = GraphNodeOut(
        id=UUID(props["id"]),
        canonical_name=props["canonical_name"],
        importance_tier=ImportanceTier(props["importance_tier"]),
        mention_count=props.get("mention_count") or 0,
        first_book_order=props.get("first_book_order"),
        first_chapter=props.get("first_chapter"),
        appears_in_books=list(props.get("appears_in_books") or []),
    )

    return node


def _refs_out(refs: list[str]) -> list[PageRefOut]:
    out = []
    for ref in refs or []:
        order, _, page = ref.partition(":")
        out.append(PageRefOut(book_order=int(order), page=int(page)))

    return out


def _edge_out(props: dict, source: str, target: str) -> GraphEdgeOut:
    edge = GraphEdgeOut(
        id=UUID(props["id"]),
        source=UUID(source),
        target=UUID(target),
        predicate=props["predicate"],
        family=RelationFamily(props["family"]),
        confidence=props["confidence"],
        evidence_count=props["evidence_count"],
        hearsay=props["hearsay"],
        page_refs=_refs_out(props.get("page_refs")),
    )

    return edge


async def get_graph(
    session: SQLModelAsyncSession,
    project_id: UUID,
    *,
    book_id: UUID | None = None,
    families: list[RelationFamily] | None = None,
    min_confidence: float = 0.0,
    limit_book_order: int | None = None,
    limit_chapter: int | None = None,
) -> GraphOut:
    """Return a project's graph from Neo4j, falling back to Postgres if it is down.

    Edges are the stored direction only: materialised inverses are for
    traversal and would draw every relation twice.

    Args:
        session: Postgres session, used only for the fallback.
        project_id: The project to render.
        book_id: Restrict to edges a book evidences.
        families: Restrict to these families.
        min_confidence: Drop edges below this confidence.
        limit_book_order: Reading position, book. ``None`` means no limit.
        limit_chapter: Reading position, chapter.

    Returns:
        Nodes, edges and whether the edge cap truncated the result.
    """
    params = {
        "pid": str(project_id),
        "lbo": limit_book_order,
        "lch": limit_chapter,
        "families": [f.value for f in families] if families else None,
        "min_confidence": min_confidence,
        "book": str(book_id) if book_id else None,
        "limit": repository.GRAPH_EDGE_LIMIT + 1,
    }
    try:
        async with neo_session() as neo:
            node_rows = await (await neo.run(_NODES, **params)).data()
            edge_rows = await (await neo.run(_EDGES, **params)).data()
    except (ServiceUnavailable, Neo4jError, OSError):
        logger.warning("neo4j unavailable; serving the graph from postgres")
        graph = await repository.get_graph_from_postgres(
            session,
            project_id,
            book_id=book_id,
            families=families,
            min_confidence=min_confidence,
            limit_book_order=limit_book_order,
            limit_chapter=limit_chapter,
        )

        return graph

    truncated = len(edge_rows) > repository.GRAPH_EDGE_LIMIT
    nodes = [_node_out(row["n"]) for row in node_rows]
    visible = {node.id for node in nodes}
    edges = [
        _edge_out(row["r"], row["source"], row["target"])
        for row in edge_rows[: repository.GRAPH_EDGE_LIMIT]
    ]
    edges = [e for e in edges if e.source in visible and e.target in visible]

    return GraphOut(nodes=nodes, edges=edges, truncated=truncated)


async def get_neighbourhood(character_id: UUID, depth: int) -> GraphOut | None:
    """Return the subgraph within ``depth`` hops of a character.

    Returns:
        ``None`` when the character is not in the graph.
    """
    depth = max(1, min(depth, MAX_DEPTH))
    edges_query = f"""
    MATCH (c:Character {{id: $id}})
    MATCH (c)-[rs:RELATED*1..{depth} {{inverse: false}}]-(:Character)
    UNWIND rs AS r
    WITH DISTINCT r
    RETURN properties(r) AS r, startNode(r).id AS source, endNode(r).id AS target
    ORDER BY r.confidence DESC, r.id
    LIMIT $limit
    """
    async with neo_session() as neo:
        center = await (
            await neo.run(
                "MATCH (c:Character {id: $id}) RETURN c.id AS id", id=str(character_id)
            )
        ).single()
        if center is None:
            return None
        rows = await (
            await neo.run(
                edges_query, id=str(character_id), limit=repository.GRAPH_EDGE_LIMIT
            )
        ).data()
        ids = (
            {str(character_id)}
            | {r["source"] for r in rows}
            | {r["target"] for r in rows}
        )
        node_rows = await (
            await neo.run(
                "MATCH (c:Character) WHERE c.id IN $ids "
                "RETURN properties(c) AS n ORDER BY c.id",
                ids=sorted(ids),
            )
        ).data()

    graph = GraphOut(
        nodes=[_node_out(row["n"]) for row in node_rows],
        edges=[_edge_out(row["r"], row["source"], row["target"]) for row in rows],
    )

    return graph


async def shortest_path(
    session: SQLModelAsyncSession, from_id: UUID, to_id: UUID, max_hops: int
) -> GraphPathOut:
    """Return the shortest chain of relations between two characters.

    The hop count is capped at ``MAX_HOPS``: an uncapped shortest-path search on
    a dense graph is a self-inflicted denial of service. Every hop is a full
    ``RelationOut`` carrying its cited pages.
    """
    if from_id == to_id:
        return GraphPathOut(hops=[], found=True)

    hops = max(1, min(max_hops, MAX_HOPS))
    query = f"""
    MATCH (a:Character {{id: $a}}), (b:Character {{id: $b}})
    MATCH p = shortestPath((a)-[:RELATED*..{hops} {{inverse: false}}]-(b))
    RETURN [r IN relationships(p) | r.id] AS ids
    """
    async with neo_session() as neo:
        record = await (await neo.run(query, a=str(from_id), b=str(to_id))).single()

    if record is None:
        return GraphPathOut(hops=[], found=False)

    ordered = await repository.relations_out(
        session, [UUID(rid) for rid in record["ids"]]
    )

    return GraphPathOut(hops=ordered, found=True)

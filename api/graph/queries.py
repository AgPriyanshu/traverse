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
from ..query.scope import ReadingScope
from . import repository
from .client import session as neo_session

logger = logging.getLogger(__name__)

MAX_HOPS = 4
MAX_DEPTH = 2

# A position is visible when it is at or before the reader's. With no chapter
# limit ($lch IS NULL), every position within that book is visible regardless
# of its own first_chapter, matching graph/repository.py's reading-position
# filters (S9's fix: this previously read `$lch IS NOT NULL AND ...`, which
# inverted the intent — it showed only chapter-less positions instead of
# lifting the chapter cap entirely).
_VISIBLE = """(
  $lbo IS NULL OR {a}.first_book_order IS NULL OR {a}.first_book_order < $lbo
  OR ({a}.first_book_order = $lbo
      AND ({a}.first_chapter IS NULL
           OR $lch IS NULL
           OR {a}.first_chapter <= $lch))
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
    scope: ReadingScope,
    book_id: UUID | None = None,
    families: list[RelationFamily] | None = None,
    min_confidence: float = 0.0,
) -> GraphOut:
    """Return a project's graph from Neo4j, falling back to Postgres if it is down.

    Edges are the stored direction only: materialised inverses are for
    traversal and would draw every relation twice.

    Args:
        session: Postgres session, used only for the fallback.
        project_id: The project to render.
        scope: The reader's position. ``ReadingScope.unlimited()`` for no
            restriction — never a default, an explicit choice at the call
            site (S8.1, PRD F4.5).
        book_id: Restrict to edges a book evidences.
        families: Restrict to these families.
        min_confidence: Drop edges below this confidence.

    Returns:
        Nodes, edges and whether the edge cap truncated the result.
    """
    params = {
        "pid": str(project_id),
        "lbo": scope.book_order,
        "lch": scope.chapter,
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
            scope=scope,
            book_id=book_id,
            families=families,
            min_confidence=min_confidence,
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

    if scope.book_order is not None and edges:
        # An edge already passed the Cypher's own ``first_book_order``/
        # ``first_chapter`` check above, but its denormalised ``page_refs``
        # property was written from *every* evidence row at projection time
        # (``graph/upsert.py``) — a visible edge reasserted later in the
        # series still needs its citation pages trimmed to this reader's
        # position, the same as ``relations_out`` does for every other
        # surface (S8.1, PRD F4.5).
        pages = await repository.page_refs_for_relations(
            session, [e.id for e in edges], scope=scope
        )
        edges = [
            GraphEdgeOut(**{**e.model_dump(), "page_refs": pages.get(e.id, [])})
            for e in edges
        ]

    return GraphOut(nodes=nodes, edges=edges, truncated=truncated)


async def get_neighbourhood(
    session: SQLModelAsyncSession,
    character_id: UUID,
    depth: int,
    *,
    scope: ReadingScope,
) -> GraphOut | None:
    """Return the subgraph within ``depth`` hops of a character.

    Args:
        session: A Postgres session — used only to re-trim each edge's
            denormalised ``page_refs`` to ``scope`` (see the note below).
        character_id: The centre of the subgraph.
        depth: Hop count, capped at ``MAX_DEPTH``.
        scope: The reader's position. ``ReadingScope.unlimited()`` for no
            restriction — never a default, an explicit choice at the call
            site (S8.1, PRD F4.5). Applied to the centre character, every
            edge, and every character the edges reach: a hop into a future
            character or a future-only edge must not surface either one.

    Returns:
        ``None`` when the character is not in the graph, or not yet visible
        at ``scope`` — the same shape, deliberately (see
        ``graph/repository.py::is_character_visible``).
    """
    depth = max(1, min(depth, MAX_DEPTH))
    node_visible = _VISIBLE.format(a="c")
    edge_visible = _VISIBLE.format(a="r")
    center_query = (
        f"MATCH (c:Character {{id: $id}}) WHERE {node_visible} RETURN c.id AS id"
    )
    edges_query = (
        "MATCH (c:Character {id: $id}) "
        f"MATCH (c)-[rs:RELATED*1..{depth} {{inverse: false}}]-(:Character) "
        "UNWIND rs AS r "
        "WITH DISTINCT r "
        f"WHERE {edge_visible} "
        "RETURN properties(r) AS r, startNode(r).id AS source, endNode(r).id AS target "
        "ORDER BY r.confidence DESC, r.id "
        "LIMIT $limit"
    )
    node_query = (
        f"MATCH (c:Character) WHERE c.id IN $ids AND {node_visible} "
        "RETURN properties(c) AS n ORDER BY c.id"
    )
    params = {"id": str(character_id), "lbo": scope.book_order, "lch": scope.chapter}
    async with neo_session() as neo:
        center = await (await neo.run(center_query, **params)).single()
        if center is None:
            return None
        rows = await (
            await neo.run(edges_query, limit=repository.GRAPH_EDGE_LIMIT, **params)
        ).data()
        ids = (
            {str(character_id)}
            | {r["source"] for r in rows}
            | {r["target"] for r in rows}
        )
        node_rows = await (await neo.run(node_query, ids=sorted(ids), **params)).data()

    visible_ids = {row["n"]["id"] for row in node_rows}
    edges = [
        _edge_out(row["r"], row["source"], row["target"])
        for row in rows
        if row["source"] in visible_ids and row["target"] in visible_ids
    ]
    if scope.book_order is not None and edges:
        # See the matching note in ``get_graph``: a visible edge's own
        # denormalised ``page_refs`` still needs trimming to ``scope``.
        pages = await repository.page_refs_for_relations(
            session, [e.id for e in edges], scope=scope
        )
        edges = [
            GraphEdgeOut(**{**e.model_dump(), "page_refs": pages.get(e.id, [])})
            for e in edges
        ]
    graph = GraphOut(
        nodes=[_node_out(row["n"]) for row in node_rows],
        edges=edges,
    )

    return graph


async def shortest_path(
    session: SQLModelAsyncSession,
    from_id: UUID,
    to_id: UUID,
    max_hops: int,
    *,
    scope: ReadingScope,
) -> GraphPathOut:
    """Return the shortest chain of relations between two characters.

    The hop count is capped at ``MAX_HOPS``: an uncapped shortest-path search on
    a dense graph is a self-inflicted denial of service. Every hop is a full
    ``RelationOut`` carrying its cited pages.

    Args:
        session: An open database session, used to hydrate the hops.
        from_id: One endpoint.
        to_id: The other endpoint.
        max_hops: Requested cap, itself capped at ``MAX_HOPS``.
        scope: The reader's position. ``ReadingScope.unlimited()`` for no
            restriction — never a default, an explicit choice at the call
            site (S8.1, PRD F4.5). Both endpoints and every node and edge
            along the path must be visible, or the path does not exist yet
            as far as this reader is concerned — same shape as "not found",
            never a partial or redacted path.
    """
    if from_id == to_id:
        return GraphPathOut(hops=[], found=True)

    hops = max(1, min(max_hops, MAX_HOPS))
    node_visible = _VISIBLE.format(a="n")
    edge_visible = _VISIBLE.format(a="r")
    query = (
        "MATCH (a:Character {id: $a}), (b:Character {id: $b}) "
        f"MATCH p = shortestPath((a)-[:RELATED*..{hops}]-(b)) "
        f"WHERE all(n IN nodes(p) WHERE {node_visible}) "
        "AND all(r IN relationships(p) "
        f"WHERE r.inverse = false AND {edge_visible}) "
        "RETURN [r IN relationships(p) | r.id] AS ids"
    )
    async with neo_session() as neo:
        record = await (
            await neo.run(
                query,
                a=str(from_id),
                b=str(to_id),
                lbo=scope.book_order,
                lch=scope.chapter,
            )
        ).single()

    if record is None:
        return GraphPathOut(hops=[], found=False)

    ordered = await repository.relations_out(
        session, [UUID(rid) for rid in record["ids"]], scope=scope
    )

    return GraphPathOut(hops=ordered, found=True)

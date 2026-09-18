from dataclasses import dataclass
from uuid import UUID

from .client import session

# The projection is book-attributed on purpose. Characters and relations are
# project-scoped (one Anne across three volumes), so "delete what this book
# contributed" is only answerable if every node and edge records which books
# produced it. Without that, re-ingesting one volume of a series means dropping
# the whole project's graph.
#
#   (:Book      {id, project_id, series_order, title})
#   (:Character {id, project_id, canonical_name, importance_tier, mention_count,
#                first_book_order, first_chapter, appears_in_books: [order]})
#   (:Character)-[:APPEARS_IN {book_id, ...}]->(:Book)
#   (:Character)-[:RELATED {id, predicate, family, confidence, status,
#                           assertion_type, hearsay, evidence_count,
#                           page_refs, book_refs, first_book_order,
#                           first_chapter, last_book_order, last_chapter}]->(:Character)
#
# ``book_refs`` holds book UUIDs as strings; ``page_refs`` holds
# ``"<book_order>:<page>"`` strings, because in a series a page number without
# its volume is not a citation.


@dataclass(frozen=True)
class ResetCounts:
    relations_deleted: int
    relations_detached: int
    appearances_deleted: int
    characters_deleted: int
    books_deleted: int


_DELETE_BOOK_ONLY_RELATIONS = """
MATCH (:Character)-[r:RELATED]->(:Character)
WHERE r.book_refs IS NOT NULL
  AND $book_id IN r.book_refs
  AND size([b IN r.book_refs WHERE b <> $book_id]) = 0
DELETE r
RETURN count(*) AS deleted
"""

# An edge this book shares with another volume is not deleted: the fact still
# holds elsewhere. Its provenance is trimmed and it is marked stale so the next
# upsert recomputes the counts Postgres owns.
_DETACH_BOOK_FROM_SHARED_RELATIONS = """
MATCH (:Character)-[r:RELATED]->(:Character)
WHERE r.book_refs IS NOT NULL AND $book_id IN r.book_refs
SET r.book_refs = [b IN r.book_refs WHERE b <> $book_id],
    r.page_refs = [p IN coalesce(r.page_refs, []) WHERE NOT p STARTS WITH $page_prefix],
    r.stale = true
RETURN count(r) AS detached
"""

_DELETE_APPEARANCES = """
MATCH (:Character)-[a:APPEARS_IN]->(:Book {id: $book_id})
DELETE a
RETURN count(*) AS deleted
"""

_TRIM_APPEARS_IN_BOOKS = """
MATCH (c:Character)
WHERE $series_order IS NOT NULL
  AND c.appears_in_books IS NOT NULL
  AND $series_order IN c.appears_in_books
  AND NOT (c)-[:APPEARS_IN]->(:Book {id: $book_id})
SET c.appears_in_books = [o IN c.appears_in_books WHERE o <> $series_order]
RETURN count(c) AS trimmed
"""

# Only characters this book alone introduced are removed. A character who also
# appears in another volume survives with its remaining appearances.
_DELETE_ORPHAN_CHARACTERS = """
MATCH (c:Character)
WHERE c.project_id = $project_id AND NOT (c)-[:APPEARS_IN]->(:Book)
DETACH DELETE c
RETURN count(c) AS deleted
"""

_DELETE_BOOK = """
MATCH (b:Book {id: $book_id})
DETACH DELETE b
RETURN count(b) AS deleted
"""

_BOOK_PROJECT = """
MATCH (b:Book {id: $book_id})
RETURN b.project_id AS project_id, b.series_order AS series_order
"""

_RESET_PROJECT = """
MATCH (n)
WHERE (n:Character OR n:Book) AND n.project_id = $project_id
DETACH DELETE n
RETURN count(n) AS deleted
"""


async def _scalar(tx_result, key: str) -> int:
    record = await tx_result.single()
    value = record[key] if record is not None else 0

    return int(value or 0)


async def reset(
    book_id: UUID | str, *, project_id: UUID | str | None = None
) -> ResetCounts:
    """Delete everything one book contributed to the graph.

    Postgres is the source of truth and Neo4j is a rebuildable projection, so a
    corrupted graph must be a re-upsert rather than a data-loss incident. Edges
    and characters shared with another volume of the same series survive with
    this book's provenance removed; edges and characters this book alone
    produced are deleted outright.

    Args:
        book_id: The book whose contribution is removed.
        project_id: The owning project. Read from the ``Book`` node when
            omitted; pass it when the ``Book`` node may already be gone.

    Returns:
        What was deleted or detached, for logging and tests.
    """
    book_key = str(book_id)

    async with session() as neo:
        lookup = await neo.run(_BOOK_PROJECT, book_id=book_key)
        record = await lookup.single()
        resolved_project = str(project_id) if project_id is not None else None
        series_order = None
        if record is not None:
            resolved_project = resolved_project or record["project_id"]
            series_order = record["series_order"]

        page_prefix = f"{series_order}:" if series_order is not None else "\x00"

        deleted_relations = await _scalar(
            await neo.run(_DELETE_BOOK_ONLY_RELATIONS, book_id=book_key), "deleted"
        )
        detached_relations = await _scalar(
            await neo.run(
                _DETACH_BOOK_FROM_SHARED_RELATIONS,
                book_id=book_key,
                page_prefix=page_prefix,
            ),
            "detached",
        )
        deleted_appearances = await _scalar(
            await neo.run(_DELETE_APPEARANCES, book_id=book_key), "deleted"
        )
        trim = await neo.run(
            _TRIM_APPEARS_IN_BOOKS, book_id=book_key, series_order=series_order
        )
        await trim.consume()

        deleted_characters = 0
        if resolved_project is not None:
            deleted_characters = await _scalar(
                await neo.run(_DELETE_ORPHAN_CHARACTERS, project_id=resolved_project),
                "deleted",
            )

        deleted_books = await _scalar(
            await neo.run(_DELETE_BOOK, book_id=book_key), "deleted"
        )

    counts = ResetCounts(
        relations_deleted=deleted_relations,
        relations_detached=detached_relations,
        appearances_deleted=deleted_appearances,
        characters_deleted=deleted_characters,
        books_deleted=deleted_books,
    )

    return counts


async def reset_project(project_id: UUID | str) -> int:
    """Delete an entire project's subgraph, leaving other projects untouched.

    Args:
        project_id: The project to drop.

    Returns:
        The number of nodes deleted.
    """
    async with session() as neo:
        deleted = await _scalar(
            await neo.run(_RESET_PROJECT, project_id=str(project_id)), "deleted"
        )

    return deleted

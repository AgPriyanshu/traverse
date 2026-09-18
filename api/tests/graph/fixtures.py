import uuid

from api.graph import client

_CREATE_BOOK = """
MERGE (b:Book {id: $book_id})
SET b.project_id = $project_id, b.series_order = $series_order, b.title = $title
"""

_CREATE_CHARACTERS = """
UNWIND $rows AS row
MERGE (c:Character {id: row.id})
SET c.project_id = $project_id,
    c.canonical_name = row.canonical_name,
    c.importance_tier = 'minor',
    c.mention_count = row.mention_count,
    c.appears_in_books = row.appears_in_books
WITH c, row
MATCH (b:Book {id: row.book_id})
MERGE (c)-[a:APPEARS_IN {book_id: row.book_id}]->(b)
SET a.mention_count = row.mention_count
"""

_CREATE_RELATIONS = """
UNWIND $rows AS row
MATCH (s:Character {id: row.source}), (o:Character {id: row.target})
MERGE (s)-[r:RELATED {id: row.id}]->(o)
SET r.predicate = row.predicate,
    r.family = row.family,
    r.confidence = 0.8,
    r.status = 'active',
    r.evidence_count = 1,
    r.book_refs = row.book_refs,
    r.page_refs = row.page_refs,
    r.first_book_order = row.first_book_order,
    r.first_chapter = 1
"""


async def create_book(
    project_id: str, *, series_order: int, title: str = "Fixture"
) -> str:
    """Create a ``Book`` node and return its id.

    Args:
        project_id: Owning project.
        series_order: Position in the series; a standalone is ``1``.
        title: Book title.
    """
    book_id = str(uuid.uuid4())
    async with client.session() as neo:
        await neo.run(
            _CREATE_BOOK,
            book_id=book_id,
            project_id=project_id,
            series_order=series_order,
            title=title,
        )

    return book_id


async def create_characters(
    project_id: str, book_id: str, *, count: int, series_order: int, prefix: str
) -> list[str]:
    """Create characters appearing in one book and return their ids.

    Args:
        project_id: Owning project.
        book_id: The book they appear in.
        count: How many to create.
        series_order: The book's series position, recorded on the node.
        prefix: Canonical-name prefix, so failures name the fixture.
    """
    ids = [str(uuid.uuid4()) for _ in range(count)]
    rows = [
        {
            "id": character_id,
            "canonical_name": f"{prefix} {index}",
            "mention_count": index + 1,
            "appears_in_books": [series_order],
            "book_id": book_id,
        }
        for index, character_id in enumerate(ids)
    ]
    async with client.session() as neo:
        await neo.run(_CREATE_CHARACTERS, project_id=project_id, rows=rows)

    return ids


async def add_appearance(character_id: str, book_id: str, series_order: int) -> None:
    """Record a second book for an existing character.

    Args:
        character_id: The character.
        book_id: The additional book.
        series_order: That book's series position.
    """
    async with client.session() as neo:
        await neo.run(
            """
            MATCH (c:Character {id: $character_id}), (b:Book {id: $book_id})
            MERGE (c)-[a:APPEARS_IN {book_id: $book_id}]->(b)
            SET c.appears_in_books =
                CASE WHEN $series_order IN c.appears_in_books
                     THEN c.appears_in_books
                     ELSE c.appears_in_books + $series_order END
            """,
            character_id=character_id,
            book_id=book_id,
            series_order=series_order,
        )


async def create_relations(
    character_ids: list[str],
    *,
    count: int,
    book_ids: list[str],
    series_order: int,
    predicate: str = "friend_of",
    family: str = "social",
) -> list[str]:
    """Wire ``count`` edges over ``character_ids`` and return their ids.

    Args:
        character_ids: Nodes to connect; at least two.
        count: How many edges to create.
        book_ids: Books credited in ``book_refs``.
        series_order: Series position used for ``page_refs`` and validity.
        predicate: Edge predicate.
        family: Edge family.
    """
    rows = []
    total = len(character_ids)
    for index in range(count):
        source = character_ids[index % total]
        target = character_ids[(index * 7 + 3) % total]
        if source == target:
            target = character_ids[(index + 1) % total]
        rows.append(
            {
                "id": str(uuid.uuid4()),
                "source": source,
                "target": target,
                "predicate": predicate,
                "family": family,
                "book_refs": list(book_ids),
                "page_refs": [f"{series_order}:{index % 300 + 1}"],
                "first_book_order": series_order,
            }
        )

    async with client.session() as neo:
        await neo.run(_CREATE_RELATIONS, rows=rows)

    return [row["id"] for row in rows]


async def count_nodes(project_id: str) -> dict[str, int]:
    """Return node and edge counts for one project.

    Args:
        project_id: The project to measure.
    """
    async with client.session() as neo:
        result = await neo.run(
            """
            OPTIONAL MATCH (c:Character {project_id: $project_id})
            WITH collect(DISTINCT c) AS chars
            OPTIONAL MATCH (b:Book {project_id: $project_id})
            WITH chars, collect(DISTINCT b) AS books
            OPTIONAL MATCH (s:Character {project_id: $project_id})-[r:RELATED]->()
            WITH chars, books, collect(DISTINCT r) AS rels
            OPTIONAL MATCH (:Character {project_id: $project_id})-[a:APPEARS_IN]->()
            RETURN size(chars) AS characters, size(books) AS books,
                   size(rels) AS relations, count(DISTINCT a) AS appearances
            """,
            project_id=project_id,
        )
        record = await result.single()

    counts = {
        "characters": record["characters"],
        "books": record["books"],
        "relations": record["relations"],
        "appearances": record["appearances"],
    }

    return counts


async def orphan_count(project_id: str) -> int:
    """Return characters in a project with no remaining book appearance.

    Args:
        project_id: The project to check.
    """
    async with client.session() as neo:
        result = await neo.run(
            """
            MATCH (c:Character {project_id: $project_id})
            WHERE NOT (c)-[:APPEARS_IN]->(:Book)
            RETURN count(c) AS orphans
            """,
            project_id=project_id,
        )
        record = await result.single()

    return int(record["orphans"])

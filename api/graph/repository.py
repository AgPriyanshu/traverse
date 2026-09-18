from uuid import UUID

from sqlalchemy import func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import (
    AppearanceOut,
    CharacterDetailOut,
    CharacterOut,
    GraphEdgeOut,
    GraphNodeOut,
    GraphOut,
)
from ..contracts.enums import ImportanceTier, RelationFamily
from ..db.models.character_model import Character, CharacterAppearance
from ..db.models.project_model import Book, Project
from ..db.models.relation_model import Relation, RelationEvidence

# A force-directed view stops being readable long before this, and an uncapped
# graph query on a dense project is a self-inflicted denial of service.
GRAPH_EDGE_LIMIT = 2000


async def project_exists(session: SQLModelAsyncSession, project_id: UUID) -> bool:
    """Return whether a project row exists.

    Args:
        session: An open database session.
        project_id: The project to check.
    """
    result = await session.exec(
        select(Project.id).where(Project.id == project_id).limit(1)
    )

    return result.first() is not None


async def _appearance_orders(
    session: SQLModelAsyncSession, character_ids: list[UUID]
) -> dict[UUID, list[int]]:
    """Return each character's book series orders, ascending.

    Args:
        session: An open database session.
        character_ids: Characters to look up.
    """
    if not character_ids:
        return {}

    result = await session.exec(
        select(CharacterAppearance.character_id, Book.series_order)
        .join(Book, Book.id == CharacterAppearance.book_id)
        .where(CharacterAppearance.character_id.in_(character_ids))
        .where(Book.series_order.is_not(None))
    )

    orders: dict[UUID, set[int]] = {}
    for character_id, series_order in result.all():
        orders.setdefault(character_id, set()).add(series_order)

    return {character_id: sorted(values) for character_id, values in orders.items()}


def _to_character_out(character: Character, appears_in: list[int]) -> CharacterOut:
    return CharacterOut(
        id=character.id,
        project_id=character.project_id,
        canonical_name=character.canonical_name,
        aliases=list(character.aliases or []),
        importance_tier=character.importance_tier,
        mention_count=character.mention_count,
        first_page=character.first_page,
        first_chapter=character.first_chapter,
        first_book_id=character.first_book_id,
        appears_in_books=appears_in,
        collision_suspected=character.collision_suspected,
        human_verified=character.human_verified,
    )


async def list_characters(
    session: SQLModelAsyncSession,
    project_id: UUID,
    *,
    tier: ImportanceTier | None = None,
    q: str | None = None,
    book_id: UUID | None = None,
    limit_book_order: int | None = None,
    limit_chapter: int | None = None,
) -> list[CharacterOut]:
    """Return a project's roster, filtered.

    Args:
        session: An open database session.
        project_id: The project whose roster is returned.
        tier: Restrict to one importance tier.
        q: Alias-aware substring search over canonical name and aliases.
        book_id: Restrict to characters appearing in one book.
        limit_book_order: Reading position — book. ``None`` means no limit and
            must be an explicit choice at the call site.
        limit_chapter: Reading position — chapter within that book.

    Returns:
        Matching characters, ordered by mention count then name.
    """
    statement = select(Character).where(Character.project_id == project_id)

    if tier is not None:
        statement = statement.where(Character.importance_tier == tier)

    if q:
        pattern = f"%{q}%"
        statement = statement.where(
            or_(
                Character.canonical_name.ilike(pattern),
                func.array_to_string(Character.aliases, "\x1f").ilike(pattern),
            )
        )

    if book_id is not None:
        statement = statement.where(
            select(CharacterAppearance.id)
            .where(CharacterAppearance.character_id == Character.id)
            .where(CharacterAppearance.book_id == book_id)
            .exists()
        )

    if limit_book_order is not None:
        # Reading position is a series position, compared as a row: a character
        # first seen in book 3 must not surface for a reader on book 2, and one
        # first seen later in the current book must not surface either.
        first_book = select(Book.series_order).where(Book.id == Character.first_book_id)
        statement = statement.where(
            or_(
                first_book.scalar_subquery() < limit_book_order,
                (first_book.scalar_subquery() == limit_book_order)
                & (
                    Character.first_chapter.is_(None)
                    if limit_chapter is None
                    else Character.first_chapter <= limit_chapter
                ),
            )
        )

    statement = statement.order_by(
        Character.mention_count.desc(), Character.canonical_name
    )

    result = await session.exec(statement)
    characters = list(result.all())
    orders = await _appearance_orders(session, [item.id for item in characters])

    return [
        _to_character_out(character, orders.get(character.id, []))
        for character in characters
    ]


async def get_character(
    session: SQLModelAsyncSession, character_id: UUID
) -> CharacterDetailOut | None:
    """Return one character with its per-book appearances, or ``None``.

    Alias detail, attributes and per-chapter mention counts land in S3.6.

    Args:
        session: An open database session.
        character_id: The character to fetch.
    """
    character = await session.get(Character, character_id)
    if character is None:
        return None

    orders = await _appearance_orders(session, [character.id])
    result = await session.exec(
        select(CharacterAppearance, Book)
        .join(Book, Book.id == CharacterAppearance.book_id)
        .where(CharacterAppearance.character_id == character_id)
        .order_by(Book.series_order)
    )
    appearances = [
        AppearanceOut(
            book_id=book.id,
            series_order=book.series_order,
            book_title=book.title,
            first_page=appearance.first_page,
            first_chapter=appearance.first_chapter,
            mention_count=appearance.mention_count,
            importance_tier=appearance.importance_tier,
            surface_forms=list(appearance.surface_forms or []),
        )
        for appearance, book in result.all()
    ]

    base = _to_character_out(character, orders.get(character.id, []))

    return CharacterDetailOut(**base.model_dump(), appearances=appearances)


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
    """Return the project's graph as nodes and edges.

    Sprint 1 reads Postgres, the source of truth. S4.7 moves this to a Neo4j
    traversal so the explorer and the retriever share one store (PRD F3.6);
    the response shape does not change when it does.

    Args:
        session: An open database session.
        project_id: The project to render.
        book_id: Restrict to the slice of the standing graph one book evidences.
        families: Restrict to these predicate families.
        min_confidence: Drop edges below this confidence.
        limit_book_order: Reading position — book. ``None`` means no limit.
        limit_chapter: Reading position — chapter within that book.

    Returns:
        Nodes and edges, with ``truncated`` set when the edge cap was hit.
    """
    edge_statement = select(Relation).where(Relation.project_id == project_id)

    if families:
        edge_statement = edge_statement.where(Relation.family.in_(families))

    if min_confidence > 0.0:
        edge_statement = edge_statement.where(Relation.confidence >= min_confidence)

    if book_id is not None:
        edge_statement = edge_statement.where(
            select(RelationEvidence.id)
            .where(RelationEvidence.relation_id == Relation.id)
            .where(RelationEvidence.book_id == book_id)
            .exists()
        )

    if limit_book_order is not None:
        edge_statement = edge_statement.where(
            or_(
                Relation.first_book_order < limit_book_order,
                (Relation.first_book_order == limit_book_order)
                & (
                    Relation.first_chapter.is_(None)
                    if limit_chapter is None
                    else Relation.first_chapter <= limit_chapter
                ),
            )
        )

    edge_statement = edge_statement.order_by(
        Relation.confidence.desc(), Relation.id
    ).limit(GRAPH_EDGE_LIMIT + 1)

    result = await session.exec(edge_statement)
    relations = list(result.all())
    truncated = len(relations) > GRAPH_EDGE_LIMIT
    relations = relations[:GRAPH_EDGE_LIMIT]

    page_refs = await _page_refs(session, [relation.id for relation in relations])

    nodes = await list_characters(
        session,
        project_id,
        limit_book_order=limit_book_order,
        limit_chapter=limit_chapter,
    )
    node_ids = {node.id for node in nodes}
    # An edge whose endpoint the reading position hides must not leak the
    # hidden character back in as a dangling node id.
    relations = [
        relation
        for relation in relations
        if relation.subject_character_id in node_ids
        and relation.object_character_id in node_ids
    ]

    payload = GraphOut(
        nodes=[
            GraphNodeOut(
                id=node.id,
                canonical_name=node.canonical_name,
                importance_tier=node.importance_tier,
                mention_count=node.mention_count,
                first_chapter=node.first_chapter,
                appears_in_books=node.appears_in_books,
            )
            for node in nodes
        ],
        edges=[
            GraphEdgeOut(
                id=relation.id,
                source=relation.subject_character_id,
                target=relation.object_character_id,
                predicate=relation.predicate,
                family=relation.family,
                confidence=relation.confidence,
                evidence_count=relation.evidence_count,
                hearsay=relation.hearsay,
                page_refs=page_refs.get(relation.id, []),
            )
            for relation in relations
        ],
        truncated=truncated,
    )

    return payload


async def _page_refs(
    session: SQLModelAsyncSession, relation_ids: list[UUID]
) -> dict[UUID, list[int]]:
    """Return the first evidence page of each relation, ascending.

    Args:
        session: An open database session.
        relation_ids: Relations to collect pages for.
    """
    if not relation_ids:
        return {}

    result = await session.exec(
        select(RelationEvidence.relation_id, RelationEvidence.page_start)
        .where(RelationEvidence.relation_id.in_(relation_ids))
        .order_by(RelationEvidence.page_start)
    )

    pages: dict[UUID, list[int]] = {}
    for relation_id, page in result.all():
        bucket = pages.setdefault(relation_id, [])
        if page not in bucket:
            bucket.append(page)

    return pages

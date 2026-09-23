from typing import Any
from uuid import UUID

from sqlalchemy import func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import (
    AliasOut,
    AppearanceOut,
    AttributeOut,
    CharacterDetailOut,
    CharacterOut,
    EvidenceOut,
    GraphEdgeOut,
    GraphNodeOut,
    GraphOut,
    MentionOut,
    PageRefOut,
    RelationArcOut,
    RelationOut,
)
from ..contracts.enums import AssertionType, ImportanceTier, RelationFamily
from ..db.models.character_model import Character, CharacterAppearance, CharacterMention
from ..db.models.chunk_model import DocumentChunk
from ..db.models.project_model import Book, Chapter, Project
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


async def appearance_orders(
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


def _within_reading_position(
    series_order: int | None,
    chapter: int | None,
    *,
    limit_book_order: int | None,
    limit_chapter: int | None,
) -> bool:
    """Whether a ``(series_order, chapter)`` position is visible at a reading position.

    Mirrors the SQL predicate below and in ``retrieval/repository.py``'s
    ``_reading_position_filter``. ``series_order`` is nullable in the schema
    even though a standalone book's convention is ``(1, chapter)``
    (``data-model.md``) — a ``None`` here is treated as "no restriction", the
    same way the retrieval arm already does, rather than as a bare SQL NULL
    comparison that would silently hide every such row.
    """
    if limit_book_order is None or series_order is None:
        return True
    if series_order != limit_book_order:
        return series_order < limit_book_order
    if limit_chapter is None:
        return chapter is None

    return chapter is None or chapter <= limit_chapter


def to_character_out(character: Character, appears_in: list[int]) -> CharacterOut:
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
        # ``Book.series_order`` is nullable (standalone), and a bare NULL
        # comparison in SQL is neither true nor false — it would silently drop
        # every such character the moment a caller passed a reading position.
        # Treated as "no restriction", matching ``retrieval/repository.py``'s
        # ``_reading_position_filter``.
        first_book = select(Book.series_order).where(Book.id == Character.first_book_id)
        statement = statement.where(
            or_(
                first_book.scalar_subquery().is_(None),
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
    orders = await appearance_orders(session, [item.id for item in characters])

    return [
        to_character_out(character, orders.get(character.id, []))
        for character in characters
    ]


async def get_character(
    session: SQLModelAsyncSession,
    character_id: UUID,
    *,
    limit_book_order: int | None = None,
    limit_chapter: int | None = None,
) -> CharacterDetailOut | None:
    """Return one character with its per-book appearances, or ``None``.

    Args:
        session: An open database session.
        character_id: The character to fetch.
        limit_book_order: Reading position — book. ``None`` means no limit.
            A character not yet met at this position is hidden entirely
            (returns ``None``), the same as it would be filtered out of
            ``list_characters``, so a deep link cannot leak a future
            character past the roster filter.
        limit_chapter: Reading position — chapter within that book.

    Returns:
        The character with alias detail, attributes, appearances and a
        per-chapter mention histogram, or ``None`` if it does not exist or is
        not yet visible at the given reading position.
    """
    character = await session.get(Character, character_id)
    if character is None:
        return None

    if limit_book_order is not None:
        first_order = None
        if character.first_book_id is not None:
            first_order = (await book_orders(session, {character.first_book_id})).get(
                character.first_book_id
            )
        if not _within_reading_position(
            first_order,
            character.first_chapter,
            limit_book_order=limit_book_order,
            limit_chapter=limit_chapter,
        ):
            return None

    orders = await appearance_orders(session, [character.id])
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
        if _within_reading_position(
            book.series_order,
            appearance.first_chapter,
            limit_book_order=limit_book_order,
            limit_chapter=limit_chapter,
        )
    ]

    alias_detail = await _alias_detail(session, character.project_id, character.id)
    attributes = await _visible_attributes(
        session,
        character.attributes,
        limit_book_order=limit_book_order,
        limit_chapter=limit_chapter,
    )
    mentions_per_chapter = await _mentions_per_chapter(
        session,
        character.id,
        limit_book_order=limit_book_order,
        limit_chapter=limit_chapter,
    )

    base = to_character_out(character, orders.get(character.id, []))

    return CharacterDetailOut(
        **base.model_dump(exclude={"mentions_per_chapter"}),
        alias_detail=alias_detail,
        attributes=attributes,
        appearances=appearances,
        mentions_per_chapter=mentions_per_chapter,
    )


async def book_orders(
    session: SQLModelAsyncSession, book_ids: set[UUID]
) -> dict[UUID, int | None]:
    """Return each book's series order, keyed by id.

    Args:
        session: An open database session.
        book_ids: Books to look up.
    """
    if not book_ids:
        return {}

    result = await session.exec(
        select(Book.id, Book.series_order).where(Book.id.in_(book_ids))
    )

    return dict(result.all())


async def _chapter_number_for_page(
    session: SQLModelAsyncSession, book_id: UUID, page: int
) -> int | None:
    """Return the chapter a page falls in, or ``None`` if unresolvable.

    Args:
        session: An open database session.
        book_id: The book the page belongs to.
        page: A 1-indexed page number.
    """
    result = await session.exec(
        select(Chapter.number)
        .where(Chapter.book_id == book_id)
        .where(Chapter.page_start <= page)
        .where(Chapter.page_end >= page)
        .limit(1)
    )

    return result.first()


def _parse_attributes(raw: dict[str, Any] | None) -> list[AttributeOut]:
    """Flatten ``character.attributes`` JSONB into evidenced entries.

    Shape written by S3.5's attribute extraction: ``{label: [{"value",
    "book_id", "page"}, ...]}`` — a list per label because a stated attribute
    (age, occupation) can be reasserted with new evidence later in the series.
    An entry missing ``value`` or ``page`` is dropped rather than raised on:
    PRD F2.3's citation guarantee means an attribute this endpoint cannot cite
    must not render, not crash the endpoint.

    Args:
        raw: The character's ``attributes`` column, or ``None``.
    """
    if not raw:
        return []

    entries: list[AttributeOut] = []
    for label, values in raw.items():
        if isinstance(values, dict):
            values = [values]
        if not isinstance(values, list):
            continue

        for entry in values:
            if not isinstance(entry, dict):
                continue
            value = entry.get("value")
            page = entry.get("page")
            if value is None or page is None:
                continue

            book_id = entry.get("book_id")
            entries.append(
                AttributeOut(
                    label=label,
                    value=str(value),
                    book_id=UUID(str(book_id)) if book_id else None,
                    page=int(page),
                )
            )

    return entries


async def _visible_attributes(
    session: SQLModelAsyncSession,
    raw: dict[str, Any] | None,
    *,
    limit_book_order: int | None,
    limit_chapter: int | None,
) -> list[AttributeOut]:
    """Parse and, at a reading position, spoiler-filter a character's attributes.

    Args:
        session: An open database session.
        raw: The character's ``attributes`` column, or ``None``.
        limit_book_order: Reading position — book. ``None`` means no limit.
        limit_chapter: Reading position — chapter within that book.
    """
    entries = _parse_attributes(raw)
    if limit_book_order is None or not entries:
        return entries

    book_ids = {entry.book_id for entry in entries if entry.book_id is not None}
    orders = await book_orders(session, book_ids)

    visible: list[AttributeOut] = []
    for entry in entries:
        order = orders.get(entry.book_id) if entry.book_id is not None else None
        chapter = None
        # Same book as the reading position: an attribute carries only a page,
        # not a chapter, so resolving visibility needs one lookup — cheap here
        # since a character has at most a handful of attributes, unlike the
        # thousands of mentions the histogram below has to stay one query for.
        if order == limit_book_order:
            chapter = await _chapter_number_for_page(session, entry.book_id, entry.page)
        if _within_reading_position(
            order,
            chapter,
            limit_book_order=limit_book_order,
            limit_chapter=limit_chapter,
        ):
            visible.append(entry)

    return visible


async def _alias_detail(
    session: SQLModelAsyncSession, project_id: UUID, character_id: UUID
) -> list[AliasOut]:
    """Return one character's surface forms with counts and ambiguity.

    Args:
        session: An open database session.
        project_id: Scopes the ambiguity check to this project.
        character_id: The character whose mentions are grouped.
    """
    result = await session.exec(
        select(
            CharacterMention.surface_form,
            CharacterMention.resolution_method,
            func.count(CharacterMention.id),
        )
        .where(CharacterMention.character_id == character_id)
        .group_by(CharacterMention.surface_form, CharacterMention.resolution_method)
    )
    rows = result.all()
    if not rows:
        return []

    forms = {surface_form for surface_form, _method, _count in rows}
    ambiguous = await _ambiguous_surface_forms(session, project_id, character_id, forms)

    aliases = [
        AliasOut(
            surface_form=surface_form,
            count=count,
            resolution_method=method,
            ambiguous=surface_form in ambiguous,
        )
        for surface_form, method, count in rows
    ]
    aliases.sort(key=lambda alias: (-alias.count, alias.surface_form))

    return aliases


async def _ambiguous_surface_forms(
    session: SQLModelAsyncSession,
    project_id: UUID,
    character_id: UUID,
    forms: set[str],
) -> set[str]:
    """Return the surface forms also used by a *different* character in this project.

    "Ambiguous" here means context-dependent: the same string ("Miss Bennet")
    resolves to more than one person in the project, which is exactly what
    fe1's alias chip needs to flag rather than the resolver's confidence.

    Args:
        session: An open database session.
        project_id: Scopes the search to this project.
        character_id: Excluded — a form is not ambiguous with itself.
        forms: Candidate surface forms to check.
    """
    if not forms:
        return set()

    result = await session.exec(
        select(CharacterMention.surface_form)
        .join(Character, Character.id == CharacterMention.character_id)
        .where(Character.project_id == project_id)
        .where(CharacterMention.character_id != character_id)
        .where(CharacterMention.surface_form.in_(forms))
        .distinct()
    )

    return set(result.all())


def _mention_reading_position_filter(
    statement, *, limit_book_order: int | None, limit_chapter: int | None
):
    """Restrict a ``CharacterMention``/``Book``/``Chapter`` join to a reading position.

    Args:
        statement: A statement that has already joined ``Book`` (on
            ``CharacterMention.book_id``) and outer-joined ``Chapter``.
        limit_book_order: Reading position — book. ``None`` means no limit.
        limit_chapter: Reading position — chapter within that book.
    """
    if limit_book_order is None:
        return statement

    return statement.where(
        or_(
            Book.series_order.is_(None),
            Book.series_order < limit_book_order,
            (Book.series_order == limit_book_order)
            & (
                Chapter.number.is_(None)
                if limit_chapter is None
                else Chapter.number <= limit_chapter
            ),
        )
    )


async def _mentions_per_chapter(
    session: SQLModelAsyncSession,
    character_id: UUID,
    *,
    limit_book_order: int | None = None,
    limit_chapter: int | None = None,
) -> dict[str, int]:
    """Return a character's mention count per chapter, in one grouped query.

    fe1's mentions timeline (S3.11) needs this precomputed — building it
    client-side from paginated mentions would mean fetching every mention.

    Args:
        session: An open database session.
        character_id: The character to histogram.
        limit_book_order: Reading position — book. ``None`` means no limit.
        limit_chapter: Reading position — chapter within that book.

    Returns:
        Chapter number (as a string) to mention count. A mention whose chunk
        carries no chapter (front matter, or the known Sprint 2 gap where
        chapter detection finds none) is bucketed under ``"unknown"``.
    """
    statement = (
        select(Chapter.number, func.count(CharacterMention.id))
        .select_from(CharacterMention)
        .join(DocumentChunk, DocumentChunk.id == CharacterMention.chunk_id)
        .join(Book, Book.id == CharacterMention.book_id)
        .outerjoin(Chapter, Chapter.id == DocumentChunk.chapter_id)
        .where(CharacterMention.character_id == character_id)
    )
    statement = _mention_reading_position_filter(
        statement, limit_book_order=limit_book_order, limit_chapter=limit_chapter
    )
    statement = statement.group_by(Chapter.number)

    result = await session.exec(statement)

    histogram: dict[str, int] = {}
    for number, count in result.all():
        key = "unknown" if number is None else str(number)
        histogram[key] = histogram.get(key, 0) + count

    return histogram


def _context_snippet(
    text: str, start: int | None, end: int | None, *, pad: int = 80
) -> str | None:
    """Return a short window of ``text`` around a mention's character span.

    Args:
        text: The chunk's full text.
        start: The mention's start offset, or ``None`` if unrecorded.
        end: The mention's end offset, or ``None`` if unrecorded.
        pad: Characters of surrounding context on each side.
    """
    if start is None or end is None:
        return None

    lo = max(0, start - pad)
    hi = min(len(text), end + pad)

    return text[lo:hi]


async def list_mentions(
    session: SQLModelAsyncSession,
    character_id: UUID,
    *,
    limit: int = 50,
    offset: int = 0,
    limit_book_order: int | None = None,
    limit_chapter: int | None = None,
) -> list[MentionOut] | None:
    """Return one character's mentions, page-ordered and paginated.

    Args:
        session: An open database session.
        character_id: The character whose mentions are listed.
        limit: Rows to return.
        offset: Rows to skip — pagination is ``LIMIT``/``OFFSET`` in SQL, not
            a fetch-all-then-slice, so a 2,000-mention character never loads
            more than one page into memory.
        limit_book_order: Reading position — book. ``None`` means no limit.
        limit_chapter: Reading position — chapter within that book.

    Returns:
        Mentions ordered by page, or ``None`` if the character does not exist.
    """
    character = await session.get(Character, character_id)
    if character is None:
        return None

    statement = (
        select(CharacterMention, DocumentChunk.text)
        .join(DocumentChunk, DocumentChunk.id == CharacterMention.chunk_id)
        .join(Book, Book.id == CharacterMention.book_id)
        .outerjoin(Chapter, Chapter.id == DocumentChunk.chapter_id)
        .where(CharacterMention.character_id == character_id)
    )
    statement = _mention_reading_position_filter(
        statement, limit_book_order=limit_book_order, limit_chapter=limit_chapter
    )
    statement = (
        statement.order_by(
            CharacterMention.page,
            CharacterMention.char_start.nulls_first(),
            CharacterMention.id,
        )
        .offset(offset)
        .limit(limit)
    )

    result = await session.exec(statement)

    mentions = [
        MentionOut(
            id=mention.id,
            chunk_id=mention.chunk_id,
            book_id=mention.book_id,
            surface_form=mention.surface_form,
            page=mention.page,
            context=_context_snippet(text, mention.char_start, mention.char_end),
            resolution_method=mention.resolution_method,
        )
        for mention, text in result.all()
    ]

    return mentions


async def get_graph_from_postgres(
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
) -> dict[UUID, list[PageRefOut]]:
    """Return the evidence pages of each relation, ascending, naming their book.

    Args:
        session: An open database session.
        relation_ids: Relations to collect pages for.
    """
    if not relation_ids:
        return {}

    result = await session.exec(
        select(
            RelationEvidence.relation_id,
            RelationEvidence.book_id,
            RelationEvidence.book_order,
            RelationEvidence.page_start,
        )
        .where(RelationEvidence.relation_id.in_(relation_ids))
        .order_by(RelationEvidence.book_order, RelationEvidence.page_start)
    )

    pages: dict[UUID, list[PageRefOut]] = {}
    for relation_id, book_id, book_order, page in result.all():
        bucket = pages.setdefault(relation_id, [])
        ref = PageRefOut(book_order=book_order, book_id=book_id, page=page)
        if ref not in bucket:
            bucket.append(ref)

    return pages


async def load_projection_rows(
    session: SQLModelAsyncSession, project_id: UUID
) -> dict[str, list[dict[str, Any]]]:
    """Read everything ``graph.upsert`` projects, from Postgres, sorted.

    Returns:
        ``books``, ``characters``, ``appearances`` and ``relations`` row dicts.
        Each relation carries its evidence pages so the projection can
        denormalise ``page_refs`` without a second round trip.
    """
    books = (
        await session.exec(
            select(Book).where(Book.project_id == project_id).order_by(Book.id)
        )
    ).all()
    order_of = {b.id: (b.series_order or 1) for b in books}

    characters = (
        await session.exec(
            select(Character)
            .where(Character.project_id == project_id)
            .order_by(Character.id)
        )
    ).all()
    appearances = (
        await session.exec(
            select(CharacterAppearance)
            .where(CharacterAppearance.book_id.in_(list(order_of)))
            .order_by(CharacterAppearance.character_id, CharacterAppearance.book_id)
        )
    ).all()
    relations = (
        await session.exec(
            select(Relation)
            .where(Relation.project_id == project_id)
            .order_by(Relation.id)
        )
    ).all()
    evidence = (
        await session.exec(
            select(RelationEvidence)
            .where(RelationEvidence.relation_id.in_([r.id for r in relations]))
            .order_by(RelationEvidence.relation_id, RelationEvidence.id)
        )
    ).all()

    evidence_by_relation: dict[UUID, list[RelationEvidence]] = {}
    for item in evidence:
        evidence_by_relation.setdefault(item.relation_id, []).append(item)

    orders_by_character: dict[UUID, set[int]] = {}
    for appearance in appearances:
        orders_by_character.setdefault(appearance.character_id, set()).add(
            order_of.get(appearance.book_id, 1)
        )

    rows = {
        "books": [
            {
                "id": str(b.id),
                "project_id": str(project_id),
                "series_order": b.series_order,
                "title": b.title,
            }
            for b in books
        ],
        "characters": [
            {
                "id": str(c.id),
                "project_id": str(project_id),
                "canonical_name": c.canonical_name,
                "importance_tier": c.importance_tier.value,
                "mention_count": c.mention_count,
                "first_book_order": order_of.get(c.first_book_id),
                "first_chapter": c.first_chapter,
                "appears_in_books": sorted(orders_by_character.get(c.id, ())),
            }
            for c in characters
        ],
        "appearances": [
            {"character_id": str(a.character_id), "book_id": str(a.book_id)}
            for a in appearances
        ],
        "relations": [
            {"relation": r, "evidence": evidence_by_relation.get(r.id, [])}
            for r in relations
        ],
    }

    return rows


async def book_project_id(session: SQLModelAsyncSession, book_id: UUID) -> UUID | None:
    """Return the project a book belongs to, or ``None`` when it does not exist."""
    result = await session.exec(select(Book.project_id).where(Book.id == book_id))
    project_id = result.first()

    return project_id


async def relations_out(
    session: SQLModelAsyncSession, relation_ids: list[UUID]
) -> list[RelationOut]:
    """Hydrate relations into API rows with names and cited pages, in id order.

    Args:
        session: An open database session.
        relation_ids: The relations to load; the result keeps this order.
    """
    if not relation_ids:
        return []

    relations = {
        r.id: r
        for r in (
            await session.exec(select(Relation).where(Relation.id.in_(relation_ids)))
        ).all()
    }
    character_ids = {
        cid
        for r in relations.values()
        for cid in (r.subject_character_id, r.object_character_id)
    }
    names = dict(
        (
            await session.exec(
                select(Character.id, Character.canonical_name).where(
                    Character.id.in_(character_ids)
                )
            )
        ).all()
    )
    pages = await _page_refs(session, list(relations))

    out = [
        RelationOut(
            id=r.id,
            subject_character_id=r.subject_character_id,
            subject_name=names.get(r.subject_character_id, ""),
            predicate=r.predicate,
            object_character_id=r.object_character_id,
            object_name=names.get(r.object_character_id, ""),
            family=r.family,
            confidence=r.confidence,
            status=r.status,
            assertion_type=r.assertion_type,
            hearsay=r.hearsay,
            evidence_count=r.evidence_count,
            first_book_order=r.first_book_order,
            first_chapter=r.first_chapter,
            last_book_order=r.last_book_order,
            last_chapter=r.last_chapter,
            page_refs=pages.get(r.id, []),
        )
        for rid in relation_ids
        if (r := relations.get(rid)) is not None
    ]

    return out


async def relation_arc(
    session: SQLModelAsyncSession, a: UUID, b: UUID
) -> RelationArcOut:
    """Return every state of the pair ``(a, b)`` in temporal order.

    Direction-agnostic: ``parent_of(a, b)`` and ``child_of`` extraction
    direction never change which rows come back. A pair that never changes
    yields a single state, so callers have one code path.
    """
    ids = (
        await session.exec(
            select(Relation.id)
            .where(
                or_(
                    (Relation.subject_character_id == a)
                    & (Relation.object_character_id == b),
                    (Relation.subject_character_id == b)
                    & (Relation.object_character_id == a),
                )
            )
            .order_by(
                Relation.first_book_order,
                func.coalesce(Relation.first_chapter, 0),
                Relation.predicate,
                Relation.id,
            )
        )
    ).all()
    states = await relations_out(session, list(ids))

    return RelationArcOut(subject_character_id=a, object_character_id=b, states=states)


async def list_evidence(
    session: SQLModelAsyncSession,
    relation_id: UUID,
    *,
    limit: int,
    offset: int,
) -> list[EvidenceOut] | None:
    """Return one relation's evidence, chapter-ordered with a stable tiebreak.

    Returns:
        ``None`` when the relation does not exist.
    """
    relation = await session.get(Relation, relation_id)
    if relation is None:
        return None

    speaker = None
    if relation.asserted_by_character_id is not None:
        speaker = (
            await session.exec(
                select(Character.canonical_name).where(
                    Character.id == relation.asserted_by_character_id
                )
            )
        ).first()

    rows = (
        await session.exec(
            select(RelationEvidence, Book.title, Book.series_order)
            .join(Book, Book.id == RelationEvidence.book_id)
            .where(RelationEvidence.relation_id == relation_id)
            .order_by(
                RelationEvidence.book_order,
                func.coalesce(RelationEvidence.chapter_no, 0),
                RelationEvidence.page_start,
                RelationEvidence.id,
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()

    evidence = [
        EvidenceOut(
            id=item.id,
            book_id=item.book_id,
            book_title=title,
            series_order=series_order,
            chapter_no=item.chapter_no,
            page_start=item.page_start,
            page_end=item.page_end,
            quote=item.quote,
            assertion_type=item.assertion_type,
            asserted_by=speaker
            if item.assertion_type is AssertionType.DIALOGUE
            else None,
            confidence=item.confidence,
        )
        for item, title, series_order in rows
    ]

    return evidence

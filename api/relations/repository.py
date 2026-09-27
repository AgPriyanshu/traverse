from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.enums import ImportanceTier, ReviewStatus, ReviewTaskType
from ..contracts.graph import AggregatedRelation
from ..db.models import (
    Book,
    Character,
    CharacterAppearance,
    CharacterMention,
    Relation,
    RelationEvidence,
    ReviewTask,
)
from .aggregate import Fact
from .roster import RosterEntry, descriptor_from_attributes

# Tiers a series roster always carries, project-wide, regardless of which book
# pass 2 is reading — a later book stating a fact about an earlier book's lead
# character is the whole point of S5.5.
_ALWAYS_TIERS = (ImportanceTier.PROTAGONIST, ImportanceTier.MAJOR)


async def load_book_roster(
    session: SQLModelAsyncSession, book_id: UUID
) -> list[RosterEntry]:
    """Return the characters that appear in one book, as roster entries.

    Book-local view only — use :func:`load_project_roster` for pass 2, which
    needs the series' cross-book roster, not just this book's.
    """
    statement = (
        select(Character, CharacterAppearance.importance_tier)
        .join(CharacterAppearance, CharacterAppearance.character_id == Character.id)
        .where(CharacterAppearance.book_id == book_id)
    )
    rows = (await session.execute(statement)).all()
    entries = [
        RosterEntry(
            id=character.id,
            canonical_name=character.canonical_name,
            aliases=tuple(sorted(set(character.aliases or []))),
            tier=tier,
            descriptor=descriptor_from_attributes(character.attributes or {}),
        )
        for character, tier in rows
    ]

    return entries


async def load_project_roster(
    session: SQLModelAsyncSession, book_id: UUID
) -> list[RosterEntry]:
    """Return the project's roster for pass 2, tier-scoped to one book.

    In a series the roster pass 2 reads against is the **project's**, not the
    book's (S5.5) — that is what lets book 5 state a fact about a book-1
    character and land it on the same node. Protagonist and major characters
    are always included, project-wide; minor and mentioned characters are
    included only when this book itself has produced an appearance or a
    mention for them, so an eight-book series does not carry every walk-on
    character from book one into book eight's prompt prefix.

    Returns:
        Roster entries covering the whole project, tier-scoped to ``book_id``.
        Empty if the book does not exist.
    """
    book = await session.get(Book, book_id)
    if book is None:
        return []

    local_appearance = (
        select(CharacterAppearance.id)
        .where(CharacterAppearance.character_id == Character.id)
        .where(CharacterAppearance.book_id == book_id)
        .exists()
    )
    local_mention = (
        select(CharacterMention.id)
        .where(CharacterMention.character_id == Character.id)
        .where(CharacterMention.book_id == book_id)
        .exists()
    )
    statement = select(Character).where(
        Character.project_id == book.project_id,
        or_(
            Character.importance_tier.in_(_ALWAYS_TIERS),
            local_appearance,
            local_mention,
        ),
    )
    characters = (await session.execute(statement)).scalars().all()
    entries = [
        RosterEntry(
            id=character.id,
            canonical_name=character.canonical_name,
            aliases=tuple(sorted(set(character.aliases or []))),
            tier=character.importance_tier,
            descriptor=descriptor_from_attributes(character.attributes or {}),
        )
        for character in characters
    ]

    return entries


async def book_project_and_order(
    session: SQLModelAsyncSession, book_id: UUID
) -> tuple[UUID, int]:
    """Return ``(project_id, series position)`` for a book.

    Raises:
        LookupError: If the book does not exist.
    """
    book = await session.get(Book, book_id)
    if book is None:
        raise LookupError(f"book {book_id} not found")

    order = getattr(book, "series_order", None) or 1

    return book.project_id, order


async def chunks_with_two_characters(
    session: SQLModelAsyncSession, book_id: UUID, *, minimum: int = 2
) -> set[UUID]:
    """Return chunks that mention at least ``minimum`` distinct characters.

    The local fallback for the pass-2 prefilter: a relation between two
    characters cannot be evidenced by a chunk naming fewer than two.
    """
    statement = (
        select(CharacterMention.chunk_id)
        .where(CharacterMention.book_id == book_id)
        .group_by(CharacterMention.chunk_id)
        .having(func.count(func.distinct(CharacterMention.character_id)) >= minimum)
    )
    rows = (await session.execute(statement)).scalars().all()

    return set(rows)


async def replace_conflict_tasks(
    session: SQLModelAsyncSession,
    project_id: UUID,
    book_id: UUID,
    payloads: list[dict],
) -> int:
    """Replace this book's open ``resolve_conflict`` tasks with fresh ones."""
    existing = (
        (
            await session.execute(
                select(ReviewTask)
                .where(ReviewTask.project_id == project_id)
                .where(ReviewTask.book_id == book_id)
                .where(ReviewTask.task_type == ReviewTaskType.RESOLVE_CONFLICT)
                .where(ReviewTask.status == ReviewStatus.OPEN)
            )
        )
        .scalars()
        .all()
    )
    for task in existing:
        await session.delete(task)

    for payload in payloads:
        session.add(
            ReviewTask(
                project_id=project_id,
                book_id=book_id,
                task_type=ReviewTaskType.RESOLVE_CONFLICT,
                payload=payload,
                priority=10,
            )
        )
    await session.commit()

    return len(payloads)


async def load_project_facts(
    session: SQLModelAsyncSession,
    project_id: UUID,
    *,
    exclude_book_id: UUID | None = None,
) -> list[Fact]:
    """Return the project's standing machine-made evidence, as raw facts.

    Aggregation recomputes the whole project from raw evidence rather than
    patching edges, which is what makes ingesting book 3 before book 2 come out
    the same as the other order — and what lets a book's removal converge to a
    consistent graph through the same recompute rather than a bespoke
    "subtract one book" code path (S5.8).

    Args:
        session: An open database session.
        project_id: The project whose evidence is loaded.
        exclude_book_id: Omit one book's evidence — the shape a book's own
            pass 2 needs while its fresh extraction is still staged, so its
            facts are added back in from that run rather than the previous
            one's stale copy.
    """
    statement = (
        select(Relation, RelationEvidence)
        .join(RelationEvidence, RelationEvidence.relation_id == Relation.id)
        .where(Relation.project_id == project_id)
        .where(Relation.human_verified.is_(False))
    )
    if exclude_book_id is not None:
        statement = statement.where(RelationEvidence.book_id != exclude_book_id)

    facts = [
        Fact(
            subject_id=relation.subject_character_id,
            predicate=relation.predicate,
            object_id=relation.object_character_id,
            chunk_id=evidence.chunk_id,
            book_id=evidence.book_id,
            book_order=evidence.book_order,
            chapter=evidence.chapter_no,
            page_start=evidence.page_start,
            page_end=evidence.page_end,
            quote=evidence.quote,
            assertion_type=evidence.assertion_type,
            asserted_by_id=relation.asserted_by_character_id,
            confidence=evidence.confidence,
        )
        for relation, evidence in (await session.execute(statement)).all()
    ]

    return facts


async def load_facts_from_other_books(
    session: SQLModelAsyncSession, project_id: UUID, exclude_book_id: UUID
) -> list[Fact]:
    """Return the project's standing evidence from every book except one."""
    facts = await load_project_facts(
        session, project_id, exclude_book_id=exclude_book_id
    )

    return facts


async def replace_project_relations(
    session: SQLModelAsyncSession,
    project_id: UUID,
    relations: list[AggregatedRelation],
) -> int:
    """Replace a project's machine-made edges with a fresh aggregation.

    Reuses an existing row's id for the same ``(subject, predicate, object)``
    key rather than deleting and reinserting — the identity-stability
    invariant Sprint 4 established for ``Character`` via
    ``persist_characters`` (a rerun that regenerates a row's id
    cascade-deletes everything keyed off it and orphans any citation, review
    task or Neo4j edge id pointing at the old one). Every aggregate run,
    including the one a book removal triggers, must leave an unchanged edge's
    id unchanged.

    Human-verified edges are never deleted or overwritten (PRD F5.4): left in
    place, and an aggregated edge for the same key is skipped rather than
    duplicated.

    Returns:
        The number of relations written (inserted or updated).
    """
    existing = (
        (
            await session.execute(
                select(Relation).where(Relation.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    verified_keys = {
        (r.subject_character_id, r.predicate, r.object_character_id)
        for r in existing
        if r.human_verified
    }
    by_key = {
        (r.subject_character_id, r.predicate, r.object_character_id): r
        for r in existing
        if not r.human_verified
    }

    written = 0
    kept_ids: set[UUID] = set()
    for edge in relations:
        key = (edge.subject_character_id, edge.predicate, edge.object_character_id)
        if key in verified_keys:
            continue

        row = by_key.get(key)
        if row is None:
            row = Relation(
                project_id=project_id,
                subject_character_id=edge.subject_character_id,
                object_character_id=edge.object_character_id,
                predicate=edge.predicate,
            )
            session.add(row)

        row.family = edge.family
        row.confidence = edge.confidence
        row.status = edge.status
        row.assertion_type = edge.assertion_type
        row.asserted_by_character_id = edge.asserted_by_character_id
        row.hearsay = edge.hearsay
        row.first_book_order = edge.first.book_order
        row.first_chapter = edge.first.chapter
        row.last_book_order = edge.last.book_order if edge.last else None
        row.last_chapter = edge.last.chapter if edge.last else None
        row.evidence_count = len(edge.evidence)
        await session.flush()

        # Evidence has no external identity of its own to preserve — nothing
        # cites a bare relation_evidence.id — so it is fully replaced under
        # the now-stable parent id rather than diffed item by item.
        await session.execute(
            delete(RelationEvidence).where(RelationEvidence.relation_id == row.id)
        )
        session.add_all(
            RelationEvidence(
                relation_id=row.id,
                book_id=item.book_id,
                chunk_id=item.chunk_id,
                book_order=item.book_order,
                chapter_no=item.chapter_no,
                page_start=item.page_start,
                page_end=item.page_end,
                quote=item.quote,
                assertion_type=item.assertion_type,
                confidence=item.confidence,
            )
            for item in edge.evidence
        )
        kept_ids.add(row.id)
        written += 1

    stale_ids = [
        r.id for r in existing if not r.human_verified and r.id not in kept_ids
    ]
    if stale_ids:
        await session.execute(delete(Relation).where(Relation.id.in_(stale_ids)))

    await session.commit()

    return written

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.enums import ReviewStatus, ReviewTaskType
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


async def load_book_roster(
    session: SQLModelAsyncSession, book_id: UUID
) -> list[RosterEntry]:
    """Return the characters that appear in one book, as roster entries."""
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


async def load_facts_from_other_books(
    session: SQLModelAsyncSession, project_id: UUID, exclude_book_id: UUID
) -> list[Fact]:
    """Return the project's standing evidence from every book except one.

    Aggregation recomputes the whole project from raw evidence rather than
    patching edges, which is what makes ingesting book 3 before book 2 come out
    the same as the other order.
    """
    statement = (
        select(Relation, RelationEvidence)
        .join(RelationEvidence, RelationEvidence.relation_id == Relation.id)
        .where(Relation.project_id == project_id)
        .where(Relation.human_verified.is_(False))
        .where(RelationEvidence.book_id != exclude_book_id)
    )
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


async def replace_project_relations(
    session: SQLModelAsyncSession,
    project_id: UUID,
    relations: list[AggregatedRelation],
) -> int:
    """Replace a project's machine-made edges with a fresh aggregation.

    Human-verified edges are never deleted or overwritten (PRD F5.4): they are
    left in place and an aggregated edge for the same subject, predicate and
    object is skipped rather than duplicated.

    Returns:
        The number of relations written.
    """
    verified = {
        (r.subject_character_id, r.predicate, r.object_character_id)
        for r in (
            await session.execute(
                select(Relation)
                .where(Relation.project_id == project_id)
                .where(Relation.human_verified.is_(True))
            )
        )
        .scalars()
        .all()
    }
    await session.execute(
        delete(Relation)
        .where(Relation.project_id == project_id)
        .where(Relation.human_verified.is_(False))
    )

    written = 0
    for edge in relations:
        key = (edge.subject_character_id, edge.predicate, edge.object_character_id)
        if key in verified:
            continue

        row = Relation(
            project_id=project_id,
            subject_character_id=edge.subject_character_id,
            object_character_id=edge.object_character_id,
            predicate=edge.predicate,
            family=edge.family,
            confidence=edge.confidence,
            status=edge.status,
            assertion_type=edge.assertion_type,
            asserted_by_character_id=edge.asserted_by_character_id,
            hearsay=edge.hearsay,
            first_book_order=edge.first.book_order,
            first_chapter=edge.first.chapter,
            last_book_order=edge.last.book_order if edge.last else None,
            last_chapter=edge.last.chapter if edge.last else None,
            evidence_count=len(edge.evidence),
        )
        session.add(row)
        await session.flush()
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
        written += 1

    await session.commit()

    return written

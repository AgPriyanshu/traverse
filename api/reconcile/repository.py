import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.enums import ImportanceTier, RelationFamily, ReviewTaskType
from ..db.models import (
    Book,
    BookCharacterCandidate,
    Character,
    CharacterAppearance,
    CharacterDeath,
    CharacterMention,
    Project,
    ReconciliationDecision,
    Relation,
)
from ..extraction.aliases import choose_canonical
from ..graph.repository import appearance_orders, to_character_out
from ..pipeline.verification import raise_disagreement

logger = logging.getLogger(__name__)

# Series-wide tier is the most significant role a character ever held, not
# whichever book was reconciled last -- a protagonist in book 4 does not
# regress to "minor" because book 1 barely mentioned them.
_TIER_RANK = {
    ImportanceTier.MENTIONED: 0,
    ImportanceTier.MINOR: 1,
    ImportanceTier.MAJOR: 2,
    ImportanceTier.PROTAGONIST: 3,
}


@dataclass
class BookCluster:
    """One of this book's just-persisted characters, with its raw contexts.

    ``contexts`` is pulled from ``BookCharacterCandidate.contexts`` rather
    than ``CharacterMention`` because mentions carry no context text --
    matching and blocking both need the sentence a name appeared in.
    """

    character: Character
    contexts: list[dict]
    mention_count: int


async def get_book_order(session: SQLModelAsyncSession, book_id: UUID) -> int:
    """A standalone book, or one with no explicit order, is series position 1."""
    book = await session.get(Book, book_id)

    return book.series_order or 1 if book else 1


async def list_book_clusters(
    session: SQLModelAsyncSession, book_id: UUID
) -> list[BookCluster]:
    """This book's resolved characters, grouped by the character they resolved to.

    Reads ``BookCharacterCandidate.resolved_character_id``, written by
    ``resolve_aliases`` immediately before this stage runs.
    """
    statement = select(BookCharacterCandidate).where(
        BookCharacterCandidate.book_id == book_id,  # type: ignore[arg-type]
        BookCharacterCandidate.resolved_character_id.is_not(None),  # type: ignore[union-attr]
    )
    candidates = list((await session.execute(statement)).scalars().all())

    by_character: dict[UUID, list[BookCharacterCandidate]] = {}
    for candidate in candidates:
        by_character.setdefault(candidate.resolved_character_id, []).append(candidate)  # type: ignore[arg-type]

    character_ids = list(by_character)
    if not character_ids:
        return []

    characters = {
        c.id: c
        for c in (
            await session.execute(
                select(Character).where(Character.id.in_(character_ids))  # type: ignore[union-attr]
            )
        )
        .scalars()
        .all()
    }

    clusters = []
    for character_id, rows in by_character.items():
        character = characters.get(character_id)
        if character is None:
            continue

        clusters.append(
            BookCluster(
                character=character,
                contexts=[ctx for row in rows for ctx in row.contexts],
                mention_count=sum(row.mention_count for row in rows),
            )
        )

    return clusters


async def list_roster_characters(
    session: SQLModelAsyncSession, project_id: UUID, exclude_ids: set[UUID]
) -> list[Character]:
    """Project characters this book's clusters can be reconciled against.

    Excludes this book's own characters -- a character only just persisted
    for this book has nothing else to merge with among its own siblings; the
    within-book cascade (``resolve_aliases``) already did that.
    """
    statement = select(Character).where(Character.project_id == project_id)  # type: ignore[arg-type]
    characters = list((await session.execute(statement)).scalars().all())

    return [c for c in characters if c.id not in exclude_ids]


async def context_map_for(
    session: SQLModelAsyncSession, project_id: UUID, *, exclude_book_id: UUID
) -> dict[UUID, list[dict]]:
    """Raw contexts for every already-reconciled character, from other books.

    Keyed by ``resolved_character_id`` so a character's contexts stay found
    under its id even after an earlier merge repointed some candidates to it
    (``merge_character``).
    """
    statement = (
        select(BookCharacterCandidate)
        .join(Book, Book.id == BookCharacterCandidate.book_id)  # type: ignore[arg-type]
        .where(
            Book.project_id == project_id,  # type: ignore[arg-type]
            BookCharacterCandidate.book_id != exclude_book_id,  # type: ignore[arg-type]
            BookCharacterCandidate.resolved_character_id.is_not(None),  # type: ignore[union-attr]
        )
    )
    candidates = list((await session.execute(statement)).scalars().all())

    contexts: dict[UUID, list[dict]] = {}
    for candidate in candidates:
        contexts.setdefault(candidate.resolved_character_id, []).extend(  # type: ignore[arg-type]
            candidate.contexts
        )

    return contexts


async def list_deaths(
    session: SQLModelAsyncSession, character_ids: set[UUID]
) -> dict[UUID, list[tuple[CharacterDeath, int]]]:
    """A character's established deaths, each with its book's series order."""
    if not character_ids:
        return {}

    statement = (
        select(CharacterDeath, Book.series_order)
        .join(Book, Book.id == CharacterDeath.book_id)  # type: ignore[arg-type]
        .where(CharacterDeath.character_id.in_(character_ids))  # type: ignore[union-attr]
    )
    rows = (await session.execute(statement)).all()

    deaths: dict[UUID, list[tuple[CharacterDeath, int]]] = {}
    for death, series_order in rows:
        deaths.setdefault(death.character_id, []).append((death, series_order or 1))

    return deaths


async def list_kinship_relations(
    session: SQLModelAsyncSession, character_ids: set[UUID]
) -> dict[UUID, list[Relation]]:
    """A character's established kinship-family relations, keyed by either side."""
    if not character_ids:
        return {}

    statement = select(Relation).where(
        Relation.family == RelationFamily.KINSHIP,  # type: ignore[arg-type]
        (
            Relation.subject_character_id.in_(character_ids)  # type: ignore[union-attr]
            | Relation.object_character_id.in_(character_ids)  # type: ignore[union-attr]
        ),
    )
    relations = list((await session.execute(statement)).scalars().all())

    by_character: dict[UUID, list[Relation]] = {}
    for relation in relations:
        by_character.setdefault(relation.subject_character_id, []).append(relation)
        by_character.setdefault(relation.object_character_id, []).append(relation)

    return by_character


async def get_character(
    session: SQLModelAsyncSession, character_id: UUID
) -> Character | None:
    return await session.get(Character, character_id)


async def record_decision(
    session: SQLModelAsyncSession,
    *,
    book_id: UUID,
    cluster_key: str,
    character_id: UUID | None,
    method: str,
    confidence: float,
    blocked_by: str | None,
) -> None:
    """Write the audit row every reconcile decision owes (``api/AGENTS.md``).

    An unaudited merge, block, or new-character decision cannot be reviewed
    or measured -- this is written for every one of this book's clusters,
    whatever the outcome.
    """
    decision = ReconciliationDecision(
        book_id=book_id,
        candidate_cluster_key=cluster_key,
        character_id=character_id,
        method=method,
        confidence=confidence,
        blocked_by=blocked_by,
        decided_at=datetime.now(UTC).isoformat(),
    )
    session.add(decision)
    await session.commit()


async def queue_cross_book_review(
    session: SQLModelAsyncSession,
    *,
    project_id: UUID,
    book_id: UUID,
    candidate: Character,
    target: Character,
    reason: str,
    confidence: float,
) -> None:
    """Write the ``merge_across_books`` row a blocked cross-book match owes review.

    The governing asymmetry (``plans/sprint-5/backend-1.md``): a duplicate left
    unmerged is visible and recoverable, a false merge is silent and
    destructive, so anything in the middle band routes here rather than
    guessing.

    ``payload`` matches the frozen ``MergeAcrossBooksPayload`` shape
    (``api/contracts/api.py``, S7.2). Deduplicated on the ordered
    (candidate, target) pair -- a rerun of this book's reconciliation against
    an unchanged roster reproduces the same block every time, and a human's
    "keep separate" on it must stick (S7.5/F5.4), not queue again on the next
    ingest.
    """
    orders = await appearance_orders(session, [candidate.id, target.id])

    await raise_disagreement(
        session,
        project_id=project_id,
        book_id=book_id,
        task_type=ReviewTaskType.MERGE_ACROSS_BOOKS,
        dedup_key=f"cross_book:{candidate.id}:{target.id}",
        payload={
            "candidates": [
                to_character_out(candidate, orders.get(candidate.id, [])).model_dump(
                    mode="json"
                ),
                to_character_out(target, orders.get(target.id, [])).model_dump(
                    mode="json"
                ),
            ],
            "contexts": {},
            "similarity_score": confidence,
            "reason": reason,
        },
        priority=2,
    )


async def merge_character(
    session: SQLModelAsyncSession, *, source_id: UUID, target_id: UUID
) -> None:
    """Fold a book's freshly-created duplicate character into its project match.

    ``source_id`` is always a character ``resolve_aliases`` persisted for the
    book currently reconciling -- it cannot yet own any ``relation`` row (that
    stage runs after this one in the frozen chain), so nothing but its own
    appearance, mentions, and candidate rows need moving before the row itself
    is dropped. Reassign before delete: ``CharacterMention.character_id`` and
    ``CharacterAppearance.character_id`` cascade-delete with their character,
    and deleting first would silently discard the very evidence this merge is
    trying to keep.
    """
    await session.execute(
        update(CharacterAppearance)
        .where(CharacterAppearance.character_id == source_id)  # type: ignore[arg-type]
        .values(character_id=target_id)
    )
    await session.execute(
        update(CharacterMention)
        .where(CharacterMention.character_id == source_id)  # type: ignore[arg-type]
        .values(character_id=target_id)
    )
    await session.execute(
        update(BookCharacterCandidate)
        .where(BookCharacterCandidate.resolved_character_id == source_id)  # type: ignore[arg-type]
        .values(resolved_character_id=target_id)
    )
    await session.execute(delete(Character).where(Character.id == source_id))  # type: ignore[arg-type]
    await session.commit()


async def recompute_derived_fields(
    session: SQLModelAsyncSession, character_ids: set[UUID]
) -> None:
    """Recompute every derived field from a character's full appearance set.

    Never accumulated -- recomputing from scratch every time is what makes
    out-of-order series ingestion self-correct (S5.4): whichever order the
    books arrive in, the same set of appearances produces the same fields.

    A ``human_verified`` character's own summary fields are left untouched,
    matching ``persist_characters``' precedent -- a human's correction of a
    single field is not a license to recompute the rest of the row out from
    under it.
    """
    for character_id in character_ids:
        character = await session.get(Character, character_id)
        if character is None or character.human_verified:
            continue

        appearances = list(
            (
                await session.execute(
                    select(CharacterAppearance).where(
                        CharacterAppearance.character_id == character_id  # type: ignore[arg-type]
                    )
                )
            )
            .scalars()
            .all()
        )
        if not appearances:
            continue

        book_ids = {a.book_id for a in appearances}
        books = {
            b.id: b
            for b in (
                await session.execute(select(Book).where(Book.id.in_(book_ids)))  # type: ignore[union-attr]
            )
            .scalars()
            .all()
        }

        def series_key(
            appearance: CharacterAppearance, books: dict = books
        ) -> tuple[int, int, int]:
            book = books.get(appearance.book_id)
            book_order = book.series_order if book and book.series_order else 1

            return (
                book_order,
                appearance.first_chapter or 0,
                appearance.first_page or 0,
            )

        ordered = sorted(appearances, key=series_key)
        first, last = ordered[0], ordered[-1]

        character.first_book_id = first.book_id
        character.first_chapter = first.first_chapter
        character.first_page = first.first_page
        character.last_book_id = last.book_id
        character.last_chapter = last.last_chapter
        character.mention_count = sum(a.mention_count for a in appearances)
        character.importance_tier = max(
            (a.importance_tier for a in appearances), key=lambda t: _TIER_RANK[t]
        )

        all_forms = {form for a in appearances for form in a.surface_forms}
        form_mention_counts: dict[str, int] = {}
        for appearance in appearances:
            for form in appearance.surface_forms:
                form_mention_counts[form] = (
                    form_mention_counts.get(form, 0) + appearance.mention_count
                )

        character.aliases = sorted(all_forms)
        if all_forms:
            # A pure function of this character's full, project-wide alias
            # set, never of which book merged into which -- this is what
            # keeps the chosen canonical name the same however the series
            # was ingested (S5.4).
            chosen = choose_canonical(all_forms, form_mention_counts)
            taken = await session.execute(
                select(Character.id).where(
                    Character.project_id == character.project_id,  # type: ignore[arg-type]
                    Character.canonical_name == chosen,  # type: ignore[arg-type]
                    Character.id != character.id,  # type: ignore[arg-type]
                )
            )
            # A form this character's own appearances happen to share with a
            # DIFFERENT, already-separate character (the blocking gate kept
            # them apart on purpose) must never rename this row onto that
            # name -- the unique constraint would refuse it, and even if it
            # didn't, silently relabelling a deliberately-split character is
            # exactly the false merge S5.2's blocking gate exists to prevent.
            if taken.scalar_one_or_none() is None:
                character.canonical_name = chosen

        session.add(character)

    await session.commit()


async def bump_roster_version(session: SQLModelAsyncSession, project_id: UUID) -> None:
    """Mark the project's roster stale so the graph projection knows to rebuild."""
    await session.execute(
        update(Project)
        .where(Project.id == project_id)  # type: ignore[arg-type]
        .values(roster_version=Project.roster_version + 1)
    )
    await session.commit()

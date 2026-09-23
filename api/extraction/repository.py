"""Every database access the extraction package makes.

Tasks and pipeline code call these functions; they never build a query
inline (``api/AGENTS.md``).
"""

import logging
from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.enums import CandidateKind, ReviewTaskType
from ..db.models import (
    Book,
    BookCharacterCandidate,
    Character,
    CharacterAppearance,
    CharacterMention,
    RejectedCandidate,
    ReviewTask,
)
from .discovery import MentionCandidate

logger = logging.getLogger(__name__)


def aggregate_mentions(
    mentions: list[MentionCandidate],
) -> list[dict]:
    """Fold per-chunk mentions into one row per distinct surface form.

    Args:
        mentions: Deduplicated-within-chunk mentions from
            :func:`api.extraction.discovery.discover_mentions`.

    Returns:
        One dict per distinct ``surface_form``, ready for
        :func:`replace_candidates` — ``kind`` is the most common non-unknown
        guess across occurrences, ``mention_count`` sums every chunk's count,
        and ``contexts`` keeps one entry per occurring chunk so later stages
        (alias clustering, collision detection) still see every scene a form
        appeared in.
    """
    by_form: dict[str, dict] = {}

    for mention in mentions:
        entry = by_form.setdefault(
            mention.surface_form,
            {"surface_form": mention.surface_form, "kinds": [], "contexts": []},
        )
        entry["kinds"].append(mention.kind)
        entry["contexts"].append(
            {
                "chunk_id": str(mention.chunk_id),
                "page": mention.page,
                "chapter_number": mention.chapter_number,
                "context": mention.context,
                "count": mention.count,
            }
        )

    aggregated = []
    for entry in by_form.values():
        kinds = [k for k in entry["kinds"] if k != CandidateKind.UNKNOWN]
        kind = max(set(kinds), key=kinds.count) if kinds else CandidateKind.UNKNOWN
        mention_count = sum(c["count"] for c in entry["contexts"])
        aggregated.append(
            {
                "surface_form": entry["surface_form"],
                "kind": kind,
                "mention_count": mention_count,
                "contexts": entry["contexts"],
            }
        )

    return aggregated


async def replace_candidates(
    session: SQLModelAsyncSession, book_id: UUID, aggregated: list[dict]
) -> int:
    """Replace a book's pass-1 candidates, so a re-run overwrites rather than appends.

    Also clears this book's prior rejections: a re-run of discovery is a full
    re-classification, and a stale rejection from a previous prompt version
    should not linger once discovery has produced a fresh candidate set.

    Args:
        session: Open session; this function commits.
        book_id: Book the candidates belong to.
        aggregated: Rows from :func:`aggregate_mentions`.

    Returns:
        The number of candidate rows written.
    """
    await session.execute(
        delete(BookCharacterCandidate).where(  # type: ignore[arg-type]
            BookCharacterCandidate.book_id == book_id  # type: ignore[arg-type]
        )
    )
    await session.execute(
        delete(RejectedCandidate).where(RejectedCandidate.book_id == book_id)  # type: ignore[arg-type]
    )

    if aggregated:
        rows = [{"book_id": book_id, **row} for row in aggregated]
        await session.execute(insert(BookCharacterCandidate), rows)

    await session.commit()

    return len(aggregated)


async def list_candidates(
    session: SQLModelAsyncSession, book_id: UUID
) -> list[BookCharacterCandidate]:
    """Return a book's pass-1 candidates."""
    statement = select(BookCharacterCandidate).where(
        BookCharacterCandidate.book_id == book_id  # type: ignore[arg-type]
    )
    candidates = list((await session.execute(statement)).scalars().all())

    return candidates


async def reject_candidates(
    session: SQLModelAsyncSession,
    book_id: UUID,
    rejections: list[dict],
) -> int:
    """Move rejected candidates out of the active set and into ``rejected_candidate``.

    Every rejection is stored with its reason (F2.4) — the eval harness
    measures precision loss from it, and Sprint 7's review queue lets a human
    overturn it, so a dropped candidate must never simply disappear.

    Args:
        session: Open session; this function commits.
        book_id: Book the candidates belong to.
        rejections: Dicts with ``candidate_id``, ``kind``, ``reason``.

    Returns:
        The number of candidates rejected.
    """
    if not rejections:
        return 0

    candidate_ids = [r["candidate_id"] for r in rejections]
    statement = select(BookCharacterCandidate).where(
        BookCharacterCandidate.id.in_(candidate_ids)  # type: ignore[union-attr]
    )
    candidates = {c.id: c for c in (await session.execute(statement)).scalars().all()}

    rows = []
    for rejection in rejections:
        candidate = candidates.get(rejection["candidate_id"])

        if candidate is None:
            continue

        rows.append(
            {
                "book_id": book_id,
                "surface_form": candidate.surface_form,
                "kind": rejection["kind"],
                "reason": rejection["reason"],
                "contexts": candidate.contexts,
            }
        )

    if rows:
        await session.execute(insert(RejectedCandidate), rows)

    await session.execute(
        delete(BookCharacterCandidate).where(  # type: ignore[arg-type]
            BookCharacterCandidate.id.in_(candidate_ids)  # type: ignore[union-attr]
        )
    )
    await session.commit()

    return len(rows)


async def mark_as_person(
    session: SQLModelAsyncSession, candidate_ids: list[UUID]
) -> None:
    """Correct a candidate's stored ``kind`` to ``person`` after re-classification.

    Without this, S3.3's cascade re-reads candidates from the database and
    would silently drop one pass-1 guessed wrong ("the Bennets of
    Longbourn") — it filters on the stored ``kind``, not on rejection's
    in-memory verdict.

    Args:
        session: Open session; this function commits.
        candidate_ids: Candidates to correct.
    """
    if not candidate_ids:
        return

    await session.execute(
        update(BookCharacterCandidate)
        .where(BookCharacterCandidate.id.in_(candidate_ids))  # type: ignore[union-attr]
        .values(kind=CandidateKind.PERSON)
    )
    await session.commit()


async def list_rejected(
    session: SQLModelAsyncSession, book_id: UUID
) -> list[RejectedCandidate]:
    """Return a book's rejected candidates, for the eval harness and review."""
    statement = select(RejectedCandidate).where(
        RejectedCandidate.book_id == book_id  # type: ignore[arg-type]
    )
    rejected = list((await session.execute(statement)).scalars().all())

    return rejected


async def set_cluster_keys(
    session: SQLModelAsyncSession, assignments: dict[UUID, str]
) -> None:
    """Record which resolved cluster each surviving candidate merged into.

    Args:
        session: Open session; this function commits.
        assignments: ``candidate_id -> cluster_key``.
    """
    if not assignments:
        return

    rows = [
        {"id": candidate_id, "cluster_key": cluster_key}
        for candidate_id, cluster_key in assignments.items()
    ]
    await session.execute(update(BookCharacterCandidate), rows)
    await session.commit()


async def delete_book_characters(session: SQLModelAsyncSession, book_id: UUID) -> None:
    """Undo this book's roster contribution so ``resolve_aliases`` can replace it.

    A ``Character`` a human has already verified is left untouched even if
    this leaves it with a stale appearance — ``human_verified`` values are
    never overwritten (``api/AGENTS.md``), and Sprint 5's reconciliation, not
    this function, owns merging a re-run's output back into a verified roster.
    """
    await session.execute(
        delete(CharacterMention).where(CharacterMention.book_id == book_id)  # type: ignore[arg-type]
    )
    await session.execute(
        delete(CharacterAppearance).where(CharacterAppearance.book_id == book_id)  # type: ignore[arg-type]
    )

    book = await session.get(Book, book_id)
    if book is not None:
        orphaned = select(Character.id).where(
            Character.project_id == book.project_id,  # type: ignore[arg-type]
            Character.human_verified.is_(False),  # type: ignore[union-attr]
            ~Character.id.in_(  # type: ignore[union-attr]
                select(CharacterAppearance.character_id)
            ),
        )
        await session.execute(
            delete(Character).where(Character.id.in_(orphaned))  # type: ignore[union-attr]
        )

    await session.commit()


async def persist_characters(
    session: SQLModelAsyncSession,
    book_id: UUID,
    project_id: UUID,
    characters: list[dict],
) -> list[Character]:
    """Insert this book's resolved characters, their appearance, and their mentions.

    Args:
        session: Open session; this function commits.
        book_id: Book the roster was built from.
        project_id: Owning project — the uniqueness scope for ``canonical_name``.
        characters: One dict per resolved character (shape produced by
            ``api.extraction.characters.build_character_rows``).

    Returns:
        The persisted ``Character`` rows, in input order.
    """
    persisted: list[Character] = []

    for entry in characters:
        character = Character(
            project_id=project_id,
            canonical_name=entry["canonical_name"],
            aliases=entry["aliases"],
            importance_tier=entry["importance_tier"],
            first_book_id=book_id,
            first_chapter=entry["first_chapter"],
            first_page=entry["first_page"],
            last_book_id=book_id,
            last_chapter=entry["last_chapter"],
            mention_count=entry["mention_count"],
            attributes=entry["attributes"],
            collision_suspected=entry["collision_suspected"],
        )
        session.add(character)
        await session.flush()

        appearance = CharacterAppearance(
            character_id=character.id,
            book_id=book_id,
            first_page=entry["first_page"],
            first_chapter=entry["first_chapter"],
            last_page=entry["last_page"],
            last_chapter=entry["last_chapter"],
            mention_count=entry["mention_count"],
            importance_tier=entry["importance_tier"],
            surface_forms=entry["aliases"],
            attributes=entry["attributes"],
        )
        session.add(appearance)

        mention_rows = [
            {
                "character_id": character.id,
                "book_id": book_id,
                "chunk_id": UUID(context["chunk_id"]),
                "surface_form": context["surface_form"],
                "page": context["page"],
                "confidence": context.get("confidence"),
                "resolution_method": context["resolution_method"],
            }
            for context in entry["mentions"]
        ]
        if mention_rows:
            await session.execute(insert(CharacterMention), mention_rows)

        persisted.append(character)

    await session.commit()

    for character in persisted:
        await session.refresh(character)

    return persisted


async def queue_collision_review(
    session: SQLModelAsyncSession,
    *,
    project_id: UUID,
    book_id: UUID,
    name_a: str,
    name_b: str,
    reason: str,
) -> None:
    """Write the ``merge_characters`` row a blocked merge owes Sprint 7's queue.

    Writing the row now (rather than waiting for the review UI to exist) is
    the point: nothing about this suspected collision is recoverable later if
    it is only logged.
    """
    task = ReviewTask(
        project_id=project_id,
        book_id=book_id,
        task_type=ReviewTaskType.MERGE_CHARACTERS,
        payload={"name_a": name_a, "name_b": name_b, "reason": reason},
        priority=1,
    )
    session.add(task)
    await session.commit()

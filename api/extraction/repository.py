"""Every database access the extraction package makes.

Tasks and pipeline code call these functions; they never build a query
inline (``api/AGENTS.md``).
"""

import logging
from uuid import UUID

from sqlalchemy import and_, bindparam, delete, insert, or_, select, update
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.enums import CandidateKind, RelationStatus, ReviewTaskType
from ..db.models import (
    Book,
    BookCharacterCandidate,
    Character,
    CharacterAppearance,
    CharacterMention,
    RejectedCandidate,
    Relation,
)
from ..graph import ontology
from ..graph.repository import appearance_orders, to_character_out
from ..pipeline.verification import raise_disagreement
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

    Also clears this book's prior *unverified* rejections: a re-run of
    discovery is a full re-classification, and a stale rejection from a
    previous prompt version should not linger once discovery has produced a
    fresh candidate set.

    A rejection a human has verified (F5.4) is never deleted here, and a
    surface form discovery proposes again despite one is never re-inserted as
    a fresh candidate -- the human already answered "is this a person", and
    silently reopening it by feeding it back into pass-1 clustering would be
    exactly the kind of overwrite-by-a-later-automated-pass this story exists
    to close. Instead it raises one deduplicated ``classify_candidate`` task
    (S7.6) carrying the new evidence, so a human decides whether the fresh
    signal changes anything -- the model does not get a second vote on its
    own.

    Args:
        session: Open session; this function commits.
        book_id: Book the candidates belong to.
        aggregated: Rows from :func:`aggregate_mentions`.

    Returns:
        The number of candidate rows written.
    """
    verified_rejections = await session.execute(
        select(RejectedCandidate).where(
            RejectedCandidate.book_id == book_id,  # type: ignore[arg-type]
            RejectedCandidate.human_verified.is_(True),  # type: ignore[union-attr]
        )
    )
    verified_forms = {row.surface_form for row in verified_rejections.scalars().all()}

    kept, reopened = [], []
    for row in aggregated:
        (reopened if row["surface_form"] in verified_forms else kept).append(row)

    await session.execute(
        delete(BookCharacterCandidate).where(  # type: ignore[arg-type]
            BookCharacterCandidate.book_id == book_id  # type: ignore[arg-type]
        )
    )
    await session.execute(
        delete(RejectedCandidate)
        .where(RejectedCandidate.book_id == book_id)  # type: ignore[arg-type]
        .where(RejectedCandidate.human_verified.is_(False))  # type: ignore[union-attr]
    )

    if kept:
        rows = [{"book_id": book_id, **row} for row in kept]
        await session.execute(insert(BookCharacterCandidate), rows)

    await session.commit()

    if reopened:
        book = await session.get(Book, book_id)
        project_id = book.project_id if book is not None else None
        if project_id is not None:
            for row in reopened:
                await raise_disagreement(
                    session,
                    project_id=project_id,
                    book_id=book_id,
                    task_type=ReviewTaskType.CLASSIFY_CANDIDATE,
                    dedup_key=f"reclassify:{book_id}:{row['surface_form']}",
                    payload={
                        "surface_form": row["surface_form"],
                        "book_id": str(book_id),
                        "kind_guess": row["kind"],
                        "mention_count": row["mention_count"],
                        "contexts": [],
                        "reason": (
                            "a human classified this surface form as not a "
                            "person; a later run's discovery found it again"
                        ),
                    },
                    priority=1,
                )

    return len(kept)


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

    table = BookCharacterCandidate.__table__  # type: ignore[attr-defined]
    rows = [
        {"candidate_id": candidate_id, "key": cluster_key}
        for candidate_id, cluster_key in assignments.items()
    ]
    # A Core update by key, not an ORM bulk update: the ORM path raises
    # StaleDataError if any row was deleted by a concurrent re-run, and this
    # write has nothing to protect that a missing row would violate.
    statement = (
        update(table)
        .where(table.c.id == bindparam("candidate_id"))
        .values(cluster_key=bindparam("key"))
    )
    await session.execute(statement, rows)
    await session.commit()


async def set_resolved_character_ids(
    session: SQLModelAsyncSession, assignments: dict[UUID, UUID]
) -> None:
    """Record which persisted ``Character`` each surviving candidate resolved to.

    ``pipeline.reconcile_characters`` (S5) is the reader: it groups this book's
    candidates by ``resolved_character_id`` to recover each cluster's raw
    contexts for cross-book matching and blocking, without re-deriving them
    from ``CharacterMention`` rows that carry no context text.

    Args:
        session: Open session; this function commits.
        assignments: ``candidate_id -> character_id``.
    """
    if not assignments:
        return

    table = BookCharacterCandidate.__table__  # type: ignore[attr-defined]
    rows = [
        {"candidate_id": candidate_id, "character_id": character_id}
        for candidate_id, character_id in assignments.items()
    ]
    statement = (
        update(table)
        .where(table.c.id == bindparam("candidate_id"))
        .values(resolved_character_id=bindparam("character_id"))
    )
    await session.execute(statement, rows)
    await session.commit()


async def delete_book_characters(session: SQLModelAsyncSession, book_id: UUID) -> None:
    """Undo this book's roster contribution so ``resolve_aliases`` can replace it.

    Deliberately does **not** delete ``Character`` rows. ``persist_characters``
    reuses an existing ``(project_id, canonical_name)`` row's id rather than
    replacing it, which is what keeps that character's id — and every
    ``relation``, ``CharacterMention`` and evidence row keyed off it — stable
    across a rerun. Deleting it here, even for an instant before the rerun
    recreates it, previously regenerated the id every time and cascade-deleted
    every ``relation`` that named it (Postgres ``ON DELETE CASCADE`` on
    ``relation.subject_character_id``/``object_character_id``) while Neo4j —
    upserted from an earlier run — kept the old id, 404ing every evidence
    lookup until a full pass-2 re-run replaced it (see
    ``plans/sprint-4/SCR.md``, the fe1 finding). A ``Character`` no longer
    produced by any book's roster is removed by
    :func:`sweep_orphaned_characters`, called after the new roster is
    persisted, not before it.

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

    await session.commit()


async def sweep_orphaned_characters(
    session: SQLModelAsyncSession, project_id: UUID
) -> None:
    """Delete a project's unverified ``Character`` rows no book's roster claims.

    Must run **after** :func:`persist_characters` commits the new roster, not
    before — a character this rerun still resolves has no ``CharacterAppearance``
    for the instant between :func:`delete_book_characters`'s wipe and its own
    re-persist, and sweeping on that window is exactly the delete-then-recreate
    bug this ordering exists to avoid (see :func:`delete_book_characters`).
    """
    orphaned = select(Character.id).where(
        Character.project_id == project_id,  # type: ignore[arg-type]
        Character.human_verified.is_(False),  # type: ignore[union-attr]
        ~Character.id.in_(select(CharacterAppearance.character_id)),  # type: ignore[union-attr]
    )
    await session.execute(delete(Character).where(Character.id.in_(orphaned)))  # type: ignore[union-attr]
    await session.commit()


async def _replace_appearance_and_mentions(
    session: SQLModelAsyncSession,
    character: Character,
    book_id: UUID,
    entry: dict,
) -> None:
    """Write this book's appearance and mentions for an already-persisted ``Character``.

    ``delete_book_characters`` already cleared this book's prior appearance
    and mentions, so this only ever inserts.
    """
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


async def persist_characters(
    session: SQLModelAsyncSession,
    book_id: UUID,
    project_id: UUID,
    characters: list[dict],
) -> list[Character]:
    """Upsert this book's resolved characters and rewrite their appearance/mentions.

    A resolved cluster reuses the existing ``Character`` row for its
    ``(project_id, canonical_name)`` — the same pair the table's own unique
    constraint treats as one identity — rather than always inserting a new
    row. A rerun of ``resolve_aliases`` with no roster change must be
    idempotent in the strong sense: the same person keeps the same id, not
    merely the same fields, because everything from ``relation`` rows to the
    Neo4j projection is keyed on it (see ``delete_book_characters`` for what
    goes wrong when it isn't). Only a canonical name genuinely new to the
    project gets a fresh id.

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
        character = (
            await session.execute(
                select(Character).where(
                    Character.project_id == project_id,  # type: ignore[arg-type]
                    Character.canonical_name == entry["canonical_name"],  # type: ignore[arg-type]
                )
            )
        ).scalar_one_or_none()

        if character is None:
            character = Character(
                project_id=project_id, canonical_name=entry["canonical_name"]
            )
        elif character.human_verified:
            # A human's own edit is never overwritten by a rerun
            # (``api/AGENTS.md``) -- only its appearance and mentions refresh.
            #
            # S7.6 wants a fresh review task raised whenever the rerun's own
            # proposal for `aliases`/`importance_tier` disagrees with what is
            # stored here, not just a silent skip. None of the six frozen
            # `ReviewTaskType` payload shapes (`api/contracts/api.py`, S7.2)
            # can carry "one character, old value vs. proposed value" --
            # `merge_characters` requires two *distinct* persisted characters,
            # and reusing it with the same id twice risks a resolution handler
            # actually merging the row into itself. Logged instead of guessed
            # at; SCR-1 in `plans/sprint-7/SCR.md` asks for a `confirm_field`
            # payload type at the next freeze to close this properly.
            if (
                set(character.aliases or []) != set(entry["aliases"])
                or character.importance_tier != entry["importance_tier"]
            ):
                logger.warning(
                    "verified character %s (%s) disagrees with rerun proposal "
                    "for book %s -- kept verified values, no review task "
                    "raised (see plans/sprint-7/SCR.md SCR-1)",
                    character.id,
                    character.canonical_name,
                    book_id,
                )
            session.add(character)
            await session.flush()
            await _replace_appearance_and_mentions(session, character, book_id, entry)
            persisted.append(character)
            continue

        character.aliases = entry["aliases"]
        character.importance_tier = entry["importance_tier"]
        character.first_book_id = character.first_book_id or book_id
        character.first_chapter = entry["first_chapter"]
        character.first_page = entry["first_page"]
        character.last_book_id = book_id
        character.last_chapter = entry["last_chapter"]
        character.mention_count = entry["mention_count"]
        character.attributes = entry["attributes"]
        character.collision_suspected = entry["collision_suspected"]

        session.add(character)
        await session.flush()
        await _replace_appearance_and_mentions(session, character, book_id, entry)
        persisted.append(character)

    await session.commit()

    for character in persisted:
        await session.refresh(character)

    return persisted


async def list_project_roster(
    session: SQLModelAsyncSession, project_id: UUID
) -> list[Character]:
    """Return every character in a project, for query-time name resolution (S6.7).

    Full ORM rows rather than a narrower column projection: the resolution
    cascade needs ``canonical_name``, ``aliases`` and ``importance_tier``
    together, and even a long series' roster is small enough (dozens to a few
    hundred rows) that the extra columns cost nothing measurable against the
    <50ms budget.
    """
    statement = select(Character).where(Character.project_id == project_id)
    roster = list((await session.execute(statement)).scalars().all())

    return roster


async def kinship_candidates(
    session: SQLModelAsyncSession,
    *,
    project_id: UUID,
    referent_id: UUID,
    predicate: str,
) -> list[UUID]:
    """Return every character related to ``referent_id`` by ``predicate`` (S6.7).

    ``predicate`` is read as if ``referent_id`` were its subject — "referent
    ``predicate`` candidate", e.g. ``child_of`` for "her mother". The query
    also matches the row stored the other way round, under the ontology's
    inverse: S4's aggregation canonicalises a symmetric or inverse pair onto
    a single stored direction, and query-time code cannot know which one a
    given fact landed on.

    Args:
        session: An open database session.
        project_id: Scopes the search to one project's roster.
        referent_id: The character a relative term is anchored to — S6.7's
            "her" in "her sister".
        predicate: An ontology predicate: ``sibling_of`` for "sister"/
            "brother", ``married_to`` for "wife"/"husband", ``child_of`` for
            "mother"/"father", ``parent_of`` for "son"/"daughter".

    Returns:
        Candidate character ids, unordered and possibly empty.
    """
    inverse = ontology.inverse_of(predicate) or predicate
    statement = select(
        Relation.subject_character_id, Relation.object_character_id
    ).where(
        Relation.project_id == project_id,
        Relation.status == RelationStatus.ACTIVE,
        or_(
            and_(
                Relation.subject_character_id == referent_id,
                Relation.predicate == predicate,
            ),
            and_(
                Relation.object_character_id == referent_id,
                Relation.predicate == inverse,
            ),
        ),
    )
    rows = (await session.execute(statement)).all()

    return [obj if subj == referent_id else subj for subj, obj in rows]


async def queue_collision_review(
    session: SQLModelAsyncSession,
    *,
    project_id: UUID,
    book_id: UUID,
    character_a_id: UUID,
    character_b_id: UUID,
    reason: str,
) -> None:
    """Write the ``merge_characters`` row a blocked merge owes Sprint 7's queue.

    Writing the row now (rather than waiting for the review UI to exist) is
    the point: nothing about this suspected collision is recoverable later if
    it is only logged.

    ``payload`` matches the frozen ``MergeCharactersPayload`` shape
    (``api/contracts/api.py``, S7.2) -- ``candidates`` must be real, distinct,
    persisted characters. Both sides of a collision call this (S3.4 flags
    ``collision_suspected`` on both clusters), so this is deduplicated on the
    sorted character-id pair: without it, one collision would queue two
    mirror-image tasks, and a rerun of an already-reviewed pair would queue a
    third.
    """
    dedup_key = (
        f"collision:{min(character_a_id, character_b_id)}:"
        f"{max(character_a_id, character_b_id)}"
    )

    characters = (
        (
            await session.execute(
                select(Character).where(
                    Character.id.in_([character_a_id, character_b_id])
                )  # type: ignore[union-attr]
            )
        )
        .scalars()
        .all()
    )
    if len(characters) < 2:
        # One side hasn't been persisted (yet, or ever) -- nothing to compare
        # side by side. Logged, not raised: a partial pair is not a reviewable
        # decision.
        logger.warning(
            "collision review skipped for %s/%s: not both persisted",
            character_a_id,
            character_b_id,
        )
        return

    orders = await appearance_orders(session, [c.id for c in characters])
    candidates = [to_character_out(c, orders.get(c.id, [])) for c in characters]

    await raise_disagreement(
        session,
        project_id=project_id,
        book_id=book_id,
        task_type=ReviewTaskType.MERGE_CHARACTERS,
        dedup_key=dedup_key,
        payload={
            "candidates": [c.model_dump(mode="json") for c in candidates],
            "contexts": {},
            "similarity_score": None,
            "reason": reason,
        },
        priority=1,
    )

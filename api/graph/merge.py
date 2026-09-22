"""Manual character merge and split, transactional and mention-accurate.

Sprint 7's review queue calls these directly with no UI review step of its
own, so both must already be correct: a half-merged character with orphaned
mentions is worse than no merge at all.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import delete, update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import CharacterOut
from ..contracts.enums import ImportanceTier
from ..db.models.character_model import (
    BookCharacterCandidate,
    Character,
    CharacterAppearance,
    CharacterMention,
)
from ..db.models.chunk_model import DocumentChunk
from ..db.models.project_model import Chapter
from ..db.models.relation_model import Relation
from .repository import appearance_orders, book_orders, to_character_out

# Declared in most-prominent-first order (``contracts/enums.py``); a merged
# character's tier is the most prominent one that fed into it, never the
# survivor's alone — merging a protagonist's stray candidate row into itself
# must not demote it.
_TIER_RANK = {tier: rank for rank, tier in enumerate(ImportanceTier)}


class CharacterNotFoundError(LookupError):
    """A source, target, or split character id does not exist."""


class MergeValidationError(ValueError):
    """The merge or split request is invalid on its own terms."""


def _most_prominent_tier(tiers: list[ImportanceTier]) -> ImportanceTier:
    return min(tiers, key=lambda tier: _TIER_RANK[tier])


def _merge_attribute_dicts(dicts: list[dict[str, Any] | None]) -> dict[str, Any]:
    """Union attribute evidence lists across characters, deduplicated.

    Args:
        dicts: Each character's ``attributes`` column, survivor first.
    """
    merged: dict[str, list[dict[str, Any]]] = {}
    for raw in dicts:
        if not raw:
            continue
        for label, values in raw.items():
            values = [values] if isinstance(values, dict) else values
            if not isinstance(values, list):
                continue
            bucket = merged.setdefault(label, [])
            for entry in values:
                if isinstance(entry, dict) and entry not in bucket:
                    bucket.append(entry)

    return merged


async def _distinct_surface_forms(
    session: SQLModelAsyncSession, character_id: UUID
) -> list[str]:
    result = await session.exec(
        select(CharacterMention.surface_form)
        .where(CharacterMention.character_id == character_id)
        .distinct()
    )

    return sorted(result.all())


async def _repoint_relations(
    session: SQLModelAsyncSession, source_ids: set[UUID], target_id: UUID
) -> None:
    """Re-point relation edges from merged-away characters to the survivor.

    Sprint 4 is the first sprint that can write a ``relation`` row, so this is
    a no-op on every project today. It exists anyway because ``Relation``'s
    character foreign keys cascade-delete: without this, running a merge
    after S4 lands would silently destroy the merged-away character's edges
    instead of re-pointing them, and nobody would notice until the graph came
    up short an edge that used to be there.
    """
    await session.execute(
        update(Relation)
        .where(Relation.subject_character_id.in_(source_ids))
        .values(subject_character_id=target_id)
    )
    await session.execute(
        update(Relation)
        .where(Relation.object_character_id.in_(source_ids))
        .values(object_character_id=target_id)
    )
    await session.execute(
        update(Relation)
        .where(Relation.asserted_by_character_id.in_(source_ids))
        .values(asserted_by_character_id=target_id)
    )
    # A relation whose two ends just became the same person is a self-edge:
    # the check constraint refuses it, and it no longer asserts anything.
    await session.execute(
        delete(Relation).where(
            (Relation.subject_character_id == target_id)
            & (Relation.object_character_id == target_id)
        )
    )


async def _merge_appearance_rows(
    session: SQLModelAsyncSession, target_id: UUID, source_ids: set[UUID]
) -> None:
    """Fold merged-away characters' per-book appearance rows into the survivor.

    Structural only — book identity, surface forms and attributes. The
    numeric fields (pages, chapters, mention counts) are rebuilt from actual
    mentions afterwards by ``_recompute_derived_fields``, which is what makes
    the result correct rather than merely additive.
    """
    all_ids = {target_id, *source_ids}
    result = await session.exec(
        select(CharacterAppearance).where(CharacterAppearance.character_id.in_(all_ids))
    )
    by_book: dict[UUID, list[CharacterAppearance]] = {}
    for appearance in result.all():
        by_book.setdefault(appearance.book_id, []).append(appearance)

    for rows in by_book.values():
        survivor_row = next(
            (row for row in rows if row.character_id == target_id), rows[0]
        )
        for row in rows:
            if row.id == survivor_row.id:
                continue
            survivor_row.surface_forms = sorted(
                set(survivor_row.surface_forms or []) | set(row.surface_forms or [])
            )
            survivor_row.attributes = _merge_attribute_dicts(
                [survivor_row.attributes, row.attributes]
            )
            await session.delete(row)
        if survivor_row.character_id != target_id:
            survivor_row.character_id = target_id
        session.add(survivor_row)

    await session.flush()


async def _recompute_derived_fields(
    session: SQLModelAsyncSession, character: Character
) -> None:
    """Recompute a character's per-book and project-wide fields from its mentions.

    Rebuilds every ``CharacterAppearance`` row for ``character`` from its
    actual ``CharacterMention`` rows rather than adjusting stale counters —
    "recomputed from all appearances, never accumulated" is the same
    invariant that makes out-of-order series ingestion self-correct
    (data-model.md), and merge/split are just another way appearances change.
    """
    result = await session.exec(
        select(
            CharacterMention.book_id,
            CharacterMention.page,
            CharacterMention.surface_form,
            Chapter.number,
        )
        .select_from(CharacterMention)
        .join(DocumentChunk, DocumentChunk.id == CharacterMention.chunk_id)
        .outerjoin(Chapter, Chapter.id == DocumentChunk.chapter_id)
        .where(CharacterMention.character_id == character.id)
    )

    per_book: dict[UUID, dict[str, Any]] = {}
    for book_id, page, surface_form, chapter_number in result.all():
        bucket = per_book.setdefault(
            book_id, {"pages": [], "forms": set(), "chapters": []}
        )
        bucket["pages"].append(page)
        bucket["forms"].add(surface_form)
        if chapter_number is not None:
            bucket["chapters"].append((page, chapter_number))

    existing = await session.exec(
        select(CharacterAppearance).where(
            CharacterAppearance.character_id == character.id
        )
    )
    appearance_by_book = {row.book_id: row for row in existing.all()}

    for book_id, bucket in per_book.items():
        pages = sorted(bucket["pages"])
        chapters = sorted(bucket["chapters"])
        appearance = appearance_by_book.get(book_id) or CharacterAppearance(
            character_id=character.id, book_id=book_id
        )
        appearance.first_page = pages[0]
        appearance.last_page = pages[-1]
        appearance.first_chapter = chapters[0][1] if chapters else None
        appearance.last_chapter = chapters[-1][1] if chapters else None
        appearance.mention_count = len(pages)
        appearance.surface_forms = sorted(bucket["forms"])
        session.add(appearance)

    # A book with zero remaining mentions (every one moved away in a split)
    # keeps no appearance row — an appearance asserting zero mentions is not
    # a fact, it is a leftover.
    for book_id, appearance in appearance_by_book.items():
        if book_id not in per_book:
            await session.delete(appearance)

    await session.flush()

    if not per_book:
        character.mention_count = 0
        character.first_book_id = None
        character.first_chapter = None
        character.first_page = None
        character.last_book_id = None
        character.last_chapter = None

        return

    order_by_book = await book_orders(session, set(per_book.keys()))

    def sort_key(book_id: UUID) -> tuple[int, int, int]:
        order = order_by_book.get(book_id) or 0
        bucket = per_book[book_id]
        first_chapter = min((c for _p, c in bucket["chapters"]), default=-1)
        first_page = min(bucket["pages"])

        return (order, first_chapter, first_page)

    ordered_books = sorted(per_book.keys(), key=sort_key)
    first_bucket = per_book[ordered_books[0]]
    last_bucket = per_book[ordered_books[-1]]

    character.first_book_id = ordered_books[0]
    character.first_page = min(first_bucket["pages"])
    character.first_chapter = (
        min(c for _p, c in first_bucket["chapters"])
        if first_bucket["chapters"]
        else None
    )
    character.last_book_id = ordered_books[-1]
    character.last_chapter = (
        max(c for _p, c in last_bucket["chapters"]) if last_bucket["chapters"] else None
    )
    character.mention_count = sum(len(bucket["pages"]) for bucket in per_book.values())


async def merge_characters(
    session: SQLModelAsyncSession,
    *,
    source_ids: list[UUID],
    target_id: UUID,
    canonical_name: str | None = None,
) -> CharacterOut:
    """Merge ``source_ids`` into ``target_id``, in one transaction.

    Every mention, appearance, alias and attribute a source carried moves to
    the survivor; the survivor's derived fields are then recomputed from its
    real appearances rather than summed, and the sources are deleted.

    Args:
        session: An open database session. Commits on success.
        source_ids: Characters to merge away. Must not include ``target_id``.
        target_id: The survivor.
        canonical_name: Optional rename of the survivor.

    Returns:
        The merged survivor.

    Raises:
        CharacterNotFoundError: ``target_id`` or a source id does not exist.
        MergeValidationError: ``target_id`` appears in ``source_ids``, the
            characters span more than one project, or ``canonical_name``
            collides with another character already in the project.
    """
    if target_id in source_ids:
        raise MergeValidationError("target_id must not appear in source_ids")

    ids = [target_id, *source_ids]
    result = await session.exec(select(Character).where(Character.id.in_(ids)))
    by_id = {character.id: character for character in result.all()}
    missing = [str(i) for i in ids if i not in by_id]
    if missing:
        raise CharacterNotFoundError(f"character(s) not found: {', '.join(missing)}")

    target = by_id[target_id]
    sources = [by_id[source_id] for source_id in source_ids]

    if any(source.project_id != target.project_id for source in sources):
        raise MergeValidationError("all characters must belong to the same project")

    if canonical_name and canonical_name != target.canonical_name:
        collision = await session.exec(
            select(Character.id)
            .where(Character.project_id == target.project_id)
            .where(Character.canonical_name == canonical_name)
            .where(Character.id.not_in(ids))
        )
        if collision.first() is not None:
            raise MergeValidationError(
                f"canonical_name {canonical_name!r} is already in use in this project"
            )
        target.canonical_name = canonical_name

    source_ids_set = {source.id for source in sources}

    # Union aliases and attributes before the source rows are deleted — a
    # source's own canonical name may never occur as a literal mention
    # surface form (be1's clustering can normalise it), so once the row is
    # gone this is the only place it can still be recovered from.
    alias_pool = set(target.aliases or [])
    for source in sources:
        alias_pool.update(source.aliases or [])
        alias_pool.add(source.canonical_name)
    alias_pool.discard(target.canonical_name)

    attribute_pool = _merge_attribute_dicts(
        [target.attributes, *(source.attributes for source in sources)]
    )
    merged_tier = _most_prominent_tier(
        [target.importance_tier, *(source.importance_tier for source in sources)]
    )

    await session.execute(
        update(CharacterMention)
        .where(CharacterMention.character_id.in_(source_ids_set))
        .values(character_id=target.id)
    )
    await session.execute(
        update(BookCharacterCandidate)
        .where(BookCharacterCandidate.resolved_character_id.in_(source_ids_set))
        .values(resolved_character_id=target.id)
    )
    await _repoint_relations(session, source_ids_set, target.id)
    await _merge_appearance_rows(session, target.id, source_ids_set)

    for source in sources:
        await session.delete(source)

    await session.flush()

    # Every mention now points at the survivor, so this also picks up any
    # surface form that was in a source's mentions but never made it into
    # ``source.aliases`` itself (be1's cascade doesn't guarantee the two stay
    # in lockstep before a human merge intervenes).
    alias_pool.update(await _distinct_surface_forms(session, target.id))
    target.aliases = sorted(alias_pool)
    target.attributes = attribute_pool
    target.importance_tier = merged_tier
    target.human_verified = True
    await _recompute_derived_fields(session, target)

    session.add(target)
    await session.commit()
    await session.refresh(target)

    orders = await appearance_orders(session, [target.id])

    return to_character_out(target, orders.get(target.id, []))


async def split_character(
    session: SQLModelAsyncSession,
    *,
    character_id: UUID,
    mention_ids: list[UUID],
    new_canonical_name: str,
) -> list[CharacterOut]:
    """Split a subset of ``character_id``'s mentions into a new character.

    The inverse of ``merge_characters``. Both sides are always rebuilt from
    their actual ``CharacterMention`` rows rather than carried over, which is
    what makes a merge followed by a split with the original mention
    partition restore the original numbers exactly.

    Args:
        session: An open database session. Commits on success.
        character_id: The character to split. Keeps whichever mentions are
            not named in ``mention_ids``.
        mention_ids: Mentions to move to the new character. Must be a
            non-empty, proper subset of ``character_id``'s mentions.
        new_canonical_name: Canonical name for the new character.

    Returns:
        ``[source, new_character]``.

    Raises:
        CharacterNotFoundError: ``character_id`` does not exist.
        MergeValidationError: A mention id does not belong to
            ``character_id``, every one of its mentions was named (the
            source would be left empty), or ``new_canonical_name`` collides
            with another character already in the project.
    """
    source = await session.get(Character, character_id)
    if source is None:
        raise CharacterNotFoundError(f"character not found: {character_id}")

    result = await session.exec(
        select(CharacterMention.id).where(CharacterMention.character_id == character_id)
    )
    existing_ids = set(result.all())
    requested_ids = set(mention_ids)

    missing = requested_ids - existing_ids
    if missing:
        raise MergeValidationError(
            "mention(s) do not belong to character "
            f"{character_id}: {', '.join(str(i) for i in missing)}"
        )
    if requested_ids == existing_ids:
        raise MergeValidationError(
            "cannot split away every mention — the source would be left "
            "empty; delete or merge the character instead"
        )

    collision = await session.exec(
        select(Character.id)
        .where(Character.project_id == source.project_id)
        .where(Character.canonical_name == new_canonical_name)
    )
    if collision.first() is not None:
        raise MergeValidationError(
            f"canonical_name {new_canonical_name!r} is already in use in this project"
        )

    new_character = Character(
        project_id=source.project_id,
        canonical_name=new_canonical_name,
        importance_tier=source.importance_tier,
        human_verified=True,
    )
    session.add(new_character)
    await session.flush()

    move = await session.execute(
        update(CharacterMention)
        .where(CharacterMention.id.in_(requested_ids))
        .values(character_id=new_character.id)
    )
    if move.rowcount != len(requested_ids):
        raise MergeValidationError("failed to re-point every requested mention")

    source.human_verified = True

    await _recompute_derived_fields(session, source)
    await _recompute_derived_fields(session, new_character)

    source.aliases = await _distinct_surface_forms(session, source.id)
    new_character.aliases = await _distinct_surface_forms(session, new_character.id)

    session.add(source)
    session.add(new_character)
    await session.commit()
    await session.refresh(source)
    await session.refresh(new_character)

    orders = await appearance_orders(session, [source.id, new_character.id])

    return [
        to_character_out(source, orders.get(source.id, [])),
        to_character_out(new_character, orders.get(new_character.id, [])),
    ]

"""Hydrate a stored ``ReviewTask`` row into the typed payload the API promises
(S7.2, F5.2 — ``ReviewTaskPayload`` in ``api/contracts/api.py``).

A task's stored ``payload`` column is deliberately lean — the identifying
fields the queuing call site had on hand (names, ids, a reason string) — never
the full rendering. This module resolves those identifiers against *current*
character/relation state every time a task is read, rather than freezing a
snapshot at queue time: a merge target's mention count or a relation's
confidence can move between when a task is queued and when a reviewer opens
it, and re-reading beats serving a stale number the payload promises is live
("what the system would do unattended").

Also computes each task's blast-radius priority (S7.3) from the same live
data, since the inputs to "how much does this decision move" — tier, mention
count, edge count — are exactly what hydration already has to look up.
"""

from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import (
    ChapterOut,
    ClassifyCandidatePayload,
    ConfirmChapterSplitPayload,
    ConfirmRelationPayload,
    MentionOut,
    MergeAcrossBooksPayload,
    MergeCharactersPayload,
    ResolveConflictPayload,
    ReviewTaskPayload,
)
from ..contracts.enums import CandidateKind
from ..contracts.enums import ReviewTaskType as TaskType
from ..db.models import Chapter, Character
from ..db.models.review_model import ReviewTask
from ..graph import repository as graph_repository
from ..query.scope import ReadingScope
from . import priority as priority_scoring

# A reviewer resolving a merge/conflict decision needs full, unredacted
# context regardless of any reader's position — this queue is an internal
# tool, not the reader-facing query/graph surface S8.1 spoiler-scopes.
_REVIEWER_SCOPE = ReadingScope.unlimited()

# Mention contexts shown per merge candidate — enough to judge, not a full
# concordance; the reviewer clicks through for more (F5.2 "without another
# round trip" means the decision-relevant slice is inline, not everything).
_CONTEXT_SAMPLE = 5


class HydrationError(ValueError):
    """A stored task references data that no longer resolves cleanly."""


async def _character_by_name(
    session: SQLModelAsyncSession, project_id: UUID, name: str
) -> Character | None:
    result = await session.exec(
        select(Character)
        .where(Character.project_id == project_id)
        .where(Character.canonical_name == name)
    )

    return result.first()


async def _resolve_merge_characters(
    session: SQLModelAsyncSession, task: ReviewTask
) -> list[Character]:
    """Recover the characters a merge task named, however its queue call
    stored them: by id (``candidate_ids``, the general case), or by the
    canonical names collision/cross-book queuing already had on hand before
    persistence made ids available."""
    raw = task.payload or {}
    characters: list[Character] = []

    ids = raw.get("candidate_ids") or []
    if ids:
        result = await session.exec(
            select(Character).where(Character.id.in_([UUID(i) for i in ids]))
        )
        characters.extend(result.all())

    target_id = raw.get("target_character_id")
    if target_id:
        target = await session.get(Character, UUID(target_id))
        if target is not None and target not in characters:
            characters.append(target)

    for name in (raw.get("name_a"), raw.get("name_b"), raw.get("candidate_name")):
        if not name:
            continue
        found = await _character_by_name(session, task.project_id, name)
        if found is not None and found.id not in {c.id for c in characters}:
            characters.append(found)

    if len(characters) < 2:
        raise HydrationError(
            f"task {task.id}: could not resolve two candidates from {raw!r}"
        )

    return characters


async def _merge_payload(
    session: SQLModelAsyncSession, task: ReviewTask, cls: type
) -> tuple[ReviewTaskPayload, int]:
    characters = await _resolve_merge_characters(session, task)
    orders = await graph_repository.appearance_orders(
        session, [c.id for c in characters]
    )
    candidates = [
        graph_repository.to_character_out(c, orders.get(c.id, [])) for c in characters
    ]

    contexts: dict[str, list[MentionOut]] = {}
    for character in characters:
        mentions = await graph_repository.list_mentions(
            session, character.id, scope=_REVIEWER_SCOPE, limit=_CONTEXT_SAMPLE
        )
        if mentions:
            contexts[str(character.id)] = mentions

    raw = task.payload or {}
    payload = cls(
        candidates=candidates,
        contexts=contexts,
        similarity_score=raw.get("similarity_score") or raw.get("confidence"),
    )

    max_tier = priority_scoring.highest_tier(c.importance_tier for c in characters)
    cascade = sum(c.mention_count for c in characters)
    score = priority_scoring.blast_radius(
        task_type=task.task_type, max_tier=max_tier, cascade=cascade
    )

    return payload, score


async def _confirm_relation_payload(
    session: SQLModelAsyncSession, task: ReviewTask
) -> tuple[ReviewTaskPayload, int]:
    raw = task.payload or {}
    relation_id = raw.get("relation_id")
    if not relation_id:
        raise HydrationError(f"task {task.id}: payload has no relation_id")

    relations = await graph_repository.relations_out(
        session, [UUID(relation_id)], scope=_REVIEWER_SCOPE
    )
    if not relations:
        raise HydrationError(f"task {task.id}: relation {relation_id} no longer exists")
    relation = relations[0]

    evidence = (
        await graph_repository.list_evidence(
            session, relation.id, limit=10, offset=0, scope=_REVIEWER_SCOPE
        )
        or []
    )

    characters = (
        await session.exec(
            select(Character).where(
                Character.id.in_(
                    [relation.subject_character_id, relation.object_character_id]
                )
            )
        )
    ).all()
    max_tier = priority_scoring.highest_tier(c.importance_tier for c in characters)

    payload = ConfirmRelationPayload(
        relation=relation, evidence=evidence, reason=raw.get("reason", "")
    )
    score = priority_scoring.blast_radius(
        task_type=task.task_type, max_tier=max_tier, cascade=1
    )

    return payload, score


async def conflicting_relation_ids(
    session: SQLModelAsyncSession, task: ReviewTask
) -> list[UUID]:
    """Resolve a ``resolve_conflict`` task's stored ``(subject, predicate,
    object)`` triples back to current ``Relation`` ids.

    Shared by hydration (to render them) and ``resolution.py`` (to know which
    ids besides the one a reviewer picked need superseding) — one lookup, one
    place a schema change to the stored shape has to be updated.
    """
    from ..db.models.relation_model import Relation  # local: avoid a module cycle

    raw = task.payload or {}
    triples = raw.get("relations", [])
    relation_ids: list[UUID] = []
    for subject_id, predicate, object_id in triples:
        result = await session.exec(
            select(Relation.id)
            .where(Relation.project_id == task.project_id)
            .where(Relation.subject_character_id == UUID(subject_id))
            .where(Relation.predicate == predicate)
            .where(Relation.object_character_id == UUID(object_id))
        )
        found = result.first()
        if found is not None:
            relation_ids.append(found)

    return relation_ids


async def _resolve_conflict_payload(
    session: SQLModelAsyncSession, task: ReviewTask
) -> tuple[ReviewTaskPayload, int]:
    relation_ids = await conflicting_relation_ids(session, task)
    relations = await graph_repository.relations_out(
        session, relation_ids, scope=_REVIEWER_SCOPE
    )
    if len(relations) < 2:
        raise HydrationError(
            f"task {task.id}: fewer than two of its conflicting relations still exist"
        )

    evidence = {}
    for relation in relations:
        items = await graph_repository.list_evidence(
            session, relation.id, limit=10, offset=0, scope=_REVIEWER_SCOPE
        )
        evidence[str(relation.id)] = items or []

    character_ids = {r.subject_character_id for r in relations} | {
        r.object_character_id for r in relations
    }
    characters = (
        await session.exec(select(Character).where(Character.id.in_(character_ids)))
    ).all()
    max_tier = priority_scoring.highest_tier(c.importance_tier for c in characters)

    reason = (task.payload or {}).get("type", "incompatible_relations")
    payload = ResolveConflictPayload(
        conflicting=relations,
        evidence=evidence,
        reason=reason,
    )
    score = priority_scoring.blast_radius(
        task_type=task.task_type, max_tier=max_tier, cascade=len(relations)
    )

    return payload, score


async def _classify_candidate_payload(
    session: SQLModelAsyncSession, task: ReviewTask
) -> tuple[ReviewTaskPayload, int]:
    raw = task.payload or {}
    kind_guess = raw.get("kind_guess")
    contexts_raw = raw.get("contexts", [])
    contexts = [
        c if isinstance(c, MentionOut) else MentionOut.model_validate(c)
        for c in contexts_raw
    ]

    payload = ClassifyCandidatePayload(
        surface_form=raw["surface_form"],
        book_id=UUID(raw["book_id"]),
        kind_guess=CandidateKind(kind_guess) if kind_guess else None,
        mention_count=raw.get("mention_count", 0),
        contexts=contexts,
    )
    score = priority_scoring.blast_radius(
        task_type=task.task_type, max_tier=None, cascade=payload.mention_count
    )

    return payload, score


async def _confirm_chapter_split_payload(
    session: SQLModelAsyncSession, task: ReviewTask
) -> tuple[ReviewTaskPayload, int]:
    raw = task.payload or {}
    chapter_id = raw.get("chapter_id")
    if chapter_id:
        chapter = await session.get(Chapter, UUID(chapter_id))
        if chapter is None:
            raise HydrationError(
                f"task {task.id}: chapter {chapter_id} no longer exists"
            )
        chapter_out = ChapterOut(
            id=chapter.id,
            book_id=chapter.book_id,
            number=chapter.number,
            title=chapter.title,
            page_start=chapter.page_start,
            page_end=chapter.page_end,
            detection_method=chapter.detection_method,
            chunk_count=raw.get("chunk_count", 0),
        )
    else:
        chapter_out = ChapterOut.model_validate(raw["chapter"])

    payload = ConfirmChapterSplitPayload(
        chapter=chapter_out,
        preceding_text=raw.get("preceding_text", ""),
        following_text=raw.get("following_text", ""),
        confidence=raw.get("confidence"),
    )
    score = priority_scoring.blast_radius(task_type=task.task_type, max_tier=None)

    return payload, score


_HydratedPayload = tuple[ReviewTaskPayload, int]
_Builder = Callable[[SQLModelAsyncSession, ReviewTask], Awaitable[_HydratedPayload]]

_BUILDERS: dict[TaskType, _Builder] = {
    TaskType.MERGE_CHARACTERS: lambda s, t: _merge_payload(
        s, t, MergeCharactersPayload
    ),
    TaskType.MERGE_ACROSS_BOOKS: lambda s, t: _merge_payload(
        s, t, MergeAcrossBooksPayload
    ),
    TaskType.CONFIRM_RELATION: _confirm_relation_payload,
    TaskType.RESOLVE_CONFLICT: _resolve_conflict_payload,
    TaskType.CLASSIFY_CANDIDATE: _classify_candidate_payload,
    TaskType.CONFIRM_CHAPTER_SPLIT: _confirm_chapter_split_payload,
}


async def hydrate(
    session: SQLModelAsyncSession, task: ReviewTask
) -> tuple[ReviewTaskPayload, int]:
    """Return ``(typed_payload, priority)`` for one review task.

    Raises:
        HydrationError: The task references data that no longer resolves —
            e.g. a merge candidate already deleted by an earlier resolution.
            The caller should exclude the task rather than fail the whole
            list.
    """
    builder = _BUILDERS[task.task_type]

    return await builder(session, task)

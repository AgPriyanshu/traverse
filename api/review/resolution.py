import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import ReviewResolution
from ..contracts.enums import (
    CandidateKind,
    RelationStatus,
    ReviewStatus,
    ReviewTaskType,
    StageName,
)
from ..contracts.enums import ResolutionMethod as CorrectionMethod
from ..db.models import BookCharacterCandidate, Chapter
from ..db.models.relation_model import Relation
from ..db.models.review_model import CorrectionFeedback, ReviewTask
from ..graph import merge as merge_service
from ..graph import ontology
from ..tasks import ingestion_chain
from . import payloads, workflow

logger = logging.getLogger(__name__)


class UnknownDecisionError(ValueError):
    """``resolution.decision`` is not one this task type accepts."""


async def _apply_merge(
    session: SQLModelAsyncSession, task: ReviewTask, resolution: ReviewResolution
) -> None:
    """Vocabulary fixed by fe1's S7.8-S7.10 build, not be2's own choice —
    see ``plans/sprint-7/HANDOFF.md`` on ``ai/fe1/sprint-7-queue``: ``merge``
    carries ``{primary_id, merge_ids}`` (the survivor and who folds into it),
    ``keep_separate`` carries nothing.
    """
    if resolution.decision == "keep_separate":
        return
    if resolution.decision != "merge":
        raise UnknownDecisionError(resolution.decision)

    primary_id = resolution.payload.get("primary_id")
    merge_ids = resolution.payload.get("merge_ids")
    if not primary_id or not merge_ids:
        raise UnknownDecisionError(
            "merge decision needs resolution.payload.primary_id and merge_ids"
        )

    await merge_service.merge_characters(
        session,
        source_ids=[UUID(i) for i in merge_ids],
        target_id=UUID(primary_id),
    )


async def _apply_confirm_relation(
    session: SQLModelAsyncSession, task: ReviewTask, resolution: ReviewResolution
) -> None:
    raw = task.payload or {}
    relation_id = UUID(raw["relation_id"])

    if resolution.decision == "accept":
        await session.execute(
            update(Relation)
            .where(Relation.id == relation_id)
            .values(human_verified=True)
        )
    elif resolution.decision == "reject":
        # A confirmed-spurious edge never happened; ``ended``/``superseded``
        # both imply it once held, so removing the row is the correct model,
        # not a status this frozen enum has a slot for.
        await session.execute(delete(Relation).where(Relation.id == relation_id))
    elif resolution.decision == "change_predicate":
        predicate = resolution.payload.get("predicate")
        if not predicate:
            raise UnknownDecisionError(
                "change_predicate needs resolution.payload.predicate"
            )
        await session.execute(
            update(Relation)
            .where(Relation.id == relation_id)
            .values(
                predicate=predicate,
                family=ontology.family_of(predicate),
                human_verified=True,
            )
        )
    else:
        raise UnknownDecisionError(resolution.decision)

    await session.commit()


async def _apply_resolve_conflict(
    session: SQLModelAsyncSession, task: ReviewTask, resolution: ReviewResolution
) -> None:
    if resolution.decision == "accept":
        winner_id_raw = resolution.payload.get("relation_id")
        if not winner_id_raw:
            raise UnknownDecisionError("accept needs resolution.payload.relation_id")
        winner_id = UUID(winner_id_raw)

        all_ids = await payloads.conflicting_relation_ids(session, task)
        losers = [rid for rid in all_ids if rid != winner_id]

        await session.execute(
            update(Relation)
            .where(Relation.id == winner_id)
            .values(human_verified=True, status=RelationStatus.ACTIVE)
        )
        if losers:
            # Superseded, not deleted: the losing claim was real evidence of
            # something, just not the standing fact -- the same "history
            # never overwrites" rule aggregation itself follows for a legal
            # temporal transition (character-graph.md "Edge rules").
            await session.execute(
                update(Relation)
                .where(Relation.id.in_(losers))
                .values(human_verified=True, status=RelationStatus.SUPERSEDED)
            )
    elif resolution.decision == "temporal_transition":
        order = [UUID(i) for i in resolution.payload.get("order", [])]
        if len(order) < 2:
            raise UnknownDecisionError(
                "temporal_transition needs resolution.payload.order with 2+ ids"
            )

        rows = (
            await session.exec(select(Relation).where(Relation.id.in_(order)))
        ).all()
        by_id = {r.id: r for r in rows}
        for index, relation_id in enumerate(order):
            relation = by_id.get(relation_id)
            if relation is None:
                continue
            is_last = index == len(order) - 1
            values: dict[str, object] = {"human_verified": True}
            if is_last:
                values["status"] = RelationStatus.ACTIVE
            else:
                values["status"] = RelationStatus.SUPERSEDED
                successor = by_id.get(order[index + 1])
                if successor is not None:
                    values["last_book_order"] = successor.first_book_order
                    values["last_chapter"] = successor.first_chapter
            await session.execute(
                update(Relation).where(Relation.id == relation_id).values(**values)
            )
    else:
        raise UnknownDecisionError(resolution.decision)

    await session.commit()


async def _apply_classify(
    session: SQLModelAsyncSession, task: ReviewTask, resolution: ReviewResolution
) -> None:
    if resolution.decision != "classify":
        raise UnknownDecisionError(resolution.decision)

    kind_value = resolution.payload.get("kind")
    if not kind_value:
        raise UnknownDecisionError("classify needs resolution.payload.kind")
    try:
        kind = CandidateKind(kind_value)
    except ValueError as exc:
        raise UnknownDecisionError(kind_value) from exc

    raw = task.payload or {}
    candidate_id = raw.get("candidate_id")
    if candidate_id:
        await session.execute(
            update(BookCharacterCandidate)
            .where(BookCharacterCandidate.id == UUID(candidate_id))
            .values(kind=kind)
        )
        await session.commit()


async def _apply_chapter_split(
    session: SQLModelAsyncSession, task: ReviewTask, resolution: ReviewResolution
) -> None:
    if resolution.decision not in ("accept", "reject"):
        raise UnknownDecisionError(resolution.decision)

    raw = task.payload or {}
    chapter_id = raw.get("chapter_id")
    if not chapter_id:
        return

    # ``reject`` ("not a real chapter break") cannot merge/remove the chapter
    # here -- that mutates chunk-to-chapter links, be1's `api/pipeline/**`.
    # Recording the verdict is what this handler owes; the correction lands
    # in `CorrectionFeedback` below either way, which is what S7.6's re-run
    # disagreement logic and Sprint 8 calibration actually read.
    await session.execute(
        update(Chapter)
        .where(Chapter.id == UUID(chapter_id))
        .values(human_verified=True)
    )
    await session.commit()


_HANDLERS = {
    ReviewTaskType.MERGE_CHARACTERS: _apply_merge,
    ReviewTaskType.MERGE_ACROSS_BOOKS: _apply_merge,
    ReviewTaskType.CONFIRM_RELATION: _apply_confirm_relation,
    ReviewTaskType.RESOLVE_CONFLICT: _apply_resolve_conflict,
    ReviewTaskType.CLASSIFY_CANDIDATE: _apply_classify,
    ReviewTaskType.CONFIRM_CHAPTER_SPLIT: _apply_chapter_split,
}

# Which gate a task type can unblock, and which pipeline stage to re-enter
# once it does. A merge/cross-book resolution can free pass 2 to read a
# now-stable roster; a conflict resolution can free the Neo4j projection.
# The other three task types do not gate the pipeline at all.
_GATE_FOR_TASK_TYPE = {
    ReviewTaskType.MERGE_CHARACTERS: workflow.ROSTER_GATE,
    ReviewTaskType.MERGE_ACROSS_BOOKS: workflow.ROSTER_GATE,
    ReviewTaskType.RESOLVE_CONFLICT: workflow.CONFLICT_GATE,
}
_RESUME_STAGE_FOR_GATE = {
    workflow.ROSTER_GATE: StageName.EXTRACT_RELATIONS,
    workflow.CONFLICT_GATE: StageName.UPSERT_GRAPH,
}


async def _maybe_resume_pipeline(task: ReviewTask) -> None:
    """Kick the ingestion chain back into motion if this was the last thing
    blocking its gate. ``ingestion_chain(from_stage=...)`` (frozen,
    ``api/tasks.py``) only re-runs what comes after the resume point, which is
    what makes "resume" here cheap even for a book deep in a series.
    """
    gate = _GATE_FOR_TASK_TYPE.get(task.task_type)
    if gate is None or task.book_id is None:
        return

    cleared = await workflow.resume_gate(task.book_id, gate)
    if cleared:
        logger.info(
            "book %s: %s gate cleared by task %s, resuming from %s",
            task.book_id,
            gate,
            task.id,
            _RESUME_STAGE_FOR_GATE[gate].value,
        )
        stage = _RESUME_STAGE_FOR_GATE[gate]
        ingestion_chain(task.book_id, from_stage=stage).apply_async()


async def resolve(
    session: SQLModelAsyncSession, task: ReviewTask, resolution: ReviewResolution
) -> ReviewTask:
    """Apply ``resolution`` to ``task`` and resume whatever it was blocking.

    Idempotent: a task that is not ``OPEN`` by the time this runs (already
    resolved by a concurrent call) is returned unchanged, without re-running
    the handler or writing a second feedback row.
    """
    if task.status != ReviewStatus.OPEN:
        return task

    model_value = dict(task.payload or {})

    claim = await session.execute(
        update(ReviewTask)
        .where(ReviewTask.id == task.id)
        .where(ReviewTask.status == ReviewStatus.OPEN)
        .values(
            status=ReviewStatus.RESOLVED,
            resolution=resolution.model_dump(mode="json"),
            resolved_at=datetime.now(UTC),
        )
    )
    await session.commit()

    if claim.rowcount == 0:
        # Lost the race: another call already resolved this task between our
        # read and this UPDATE. Its handler already ran; ours must not.
        refreshed = await session.get(ReviewTask, task.id)

        return refreshed or task

    handler = _HANDLERS[task.task_type]
    try:
        await handler(session, task, resolution)
    except Exception:
        # The claim above already committed (needed for the concurrency
        # guard to work at all), so an invalid decision -- caught here rather
        # than by validating before the claim, which would reopen the same
        # race it closes -- must explicitly hand the task back to OPEN rather
        # than leave it stuck RESOLVED with nothing actually applied.
        await session.execute(
            update(ReviewTask)
            .where(ReviewTask.id == task.id)
            .values(status=ReviewStatus.OPEN, resolution=None, resolved_at=None)
        )
        await session.commit()
        raise

    session.add(
        CorrectionFeedback(
            project_id=task.project_id,
            review_task_id=task.id,
            task_type=task.task_type,
            model_value=model_value,
            human_value=resolution.model_dump(mode="json"),
            model_confidence=model_value.get("confidence")
            or model_value.get("similarity_score"),
            resolution_method=CorrectionMethod.HUMAN,
        )
    )
    await session.commit()
    await session.refresh(task)

    await _maybe_resume_pipeline(task)

    return task

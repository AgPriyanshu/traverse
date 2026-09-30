from __future__ import annotations

from datetime import UTC, datetime
from statistics import median
from uuid import UUID

from eval.latency_metrics import percentile
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.enums import ReviewStatus, ReviewTaskType
from ..db.models import CorrectionFeedback, ReviewTask

DEFAULT_QUEUE_DEPTH_THRESHOLD = 50
STALE_TASK_AGE_HOURS = 48

# Which pipeline stage queues each task type -- the map the correction-rate
# breakdown groups by. `confirm_relation`/`resolve_conflict` both come out of
# pass 2 (character-graph.md); the others are one stage each.
STAGE_BY_TASK_TYPE: dict[ReviewTaskType, str] = {
    ReviewTaskType.CLASSIFY_CANDIDATE: "pass1_candidate_classification",
    ReviewTaskType.MERGE_CHARACTERS: "alias_clustering",
    ReviewTaskType.MERGE_ACROSS_BOOKS: "cross_book_reconciliation",
    ReviewTaskType.CONFIRM_RELATION: "pass2_relation_extraction",
    ReviewTaskType.RESOLVE_CONFLICT: "pass2_relation_extraction",
    ReviewTaskType.CONFIRM_CHAPTER_SPLIT: "chapter_segmentation",
}


class QueueDepthByType(BaseModel):
    task_type: ReviewTaskType
    open_count: int


class TaskAgeStats(BaseModel):
    sample_count: int = 0
    p50_hours: float | None = None
    p90_hours: float | None = None
    max_hours: float | None = None


class ResolutionOutcomeMix(BaseModel):
    accepted: int = 0
    corrected: int = 0
    rejected: int = 0
    unknown: int = 0


class StageCorrectionRate(BaseModel):
    stage: str
    task_types: list[ReviewTaskType] = Field(default_factory=list)
    feedback_count: int = 0
    corrected_count: int = 0
    correction_rate: float | None = None


class ReviewMetricsOut(BaseModel):
    project_id: UUID | None = None
    generated_at: datetime
    queue_depth_total: int
    queue_depth_by_type: list[QueueDepthByType] = Field(default_factory=list)
    open_task_age: TaskAgeStats
    median_time_to_resolve_hours: float | None = None
    resolution_outcome_mix: ResolutionOutcomeMix
    correction_rate_by_stage: list[StageCorrectionRate] = Field(default_factory=list)


class StaleTaskOut(BaseModel):
    id: UUID
    task_type: ReviewTaskType
    priority: int
    age_hours: float


class OrphanedThreadOut(BaseModel):
    graph_thread_id: str
    reason: str


class ReviewAlertsOut(BaseModel):
    project_id: UUID | None = None
    generated_at: datetime
    queue_depth_threshold: int
    queue_depth_total: int
    queue_depth_breached: bool
    stale_task_threshold_hours: int
    stale_tasks: list[StaleTaskOut] = Field(default_factory=list)
    orphaned_threads: list[OrphanedThreadOut] = Field(default_factory=list)
    has_alerts: bool


def _ensure_aware(value: datetime) -> datetime:
    # asyncpg hands back naive datetimes for a `timestamptz` column read through
    # a plain `select()` rather than the ORM's own row processor -- the column
    # is UTC either way, so a bare `replace` is correct, not a guess.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _age_hours(started_at: datetime, now: datetime) -> float:
    return (now - _ensure_aware(started_at)).total_seconds() / 3600.0


async def _open_tasks(
    session: SQLModelAsyncSession, project_id: UUID | None
) -> list[ReviewTask]:
    statement = select(ReviewTask).where(ReviewTask.status == ReviewStatus.OPEN)
    if project_id is not None:
        statement = statement.where(ReviewTask.project_id == project_id)

    return list((await session.execute(statement)).scalars().all())


async def _queue_depth_by_type(
    session: SQLModelAsyncSession, project_id: UUID | None
) -> list[QueueDepthByType]:
    statement = (
        select(ReviewTask.task_type, func.count(ReviewTask.id))
        .where(ReviewTask.status == ReviewStatus.OPEN)
        .group_by(ReviewTask.task_type)
    )
    if project_id is not None:
        statement = statement.where(ReviewTask.project_id == project_id)

    rows = (await session.execute(statement)).all()

    return [
        QueueDepthByType(task_type=task_type, open_count=int(count))
        for task_type, count in rows
    ]


async def _resolution_outcome_mix(
    session: SQLModelAsyncSession, project_id: UUID | None
) -> ResolutionOutcomeMix:
    dismissed_stmt = select(func.count(ReviewTask.id)).where(
        ReviewTask.status == ReviewStatus.DISMISSED
    )
    resolved_stmt = select(ReviewTask.id).where(
        ReviewTask.status == ReviewStatus.RESOLVED
    )
    if project_id is not None:
        dismissed_stmt = dismissed_stmt.where(ReviewTask.project_id == project_id)
        resolved_stmt = resolved_stmt.where(ReviewTask.project_id == project_id)

    rejected = int((await session.execute(dismissed_stmt)).scalar_one())
    resolved_ids = list((await session.execute(resolved_stmt)).scalars().all())

    mix = ResolutionOutcomeMix(rejected=rejected)
    if not resolved_ids:
        return mix

    feedback_stmt = select(
        CorrectionFeedback.review_task_id,
        CorrectionFeedback.model_value,
        CorrectionFeedback.human_value,
    ).where(CorrectionFeedback.review_task_id.in_(resolved_ids))  # type: ignore[union-attr]
    feedback_rows = (await session.execute(feedback_stmt)).all()

    corrected_task_ids: set[UUID] = set()
    accepted_task_ids: set[UUID] = set()
    for task_id, model_value, human_value in feedback_rows:
        if task_id is None:
            continue
        if model_value != human_value:
            corrected_task_ids.add(task_id)
        else:
            accepted_task_ids.add(task_id)

    # A task with any correcting feedback row counts as corrected even if an
    # earlier row on the same task happened to match -- the human changed
    # something, which is the signal Sprint 8's calibration wants.
    accepted_task_ids -= corrected_task_ids

    for task_id in resolved_ids:
        if task_id in corrected_task_ids:
            mix.corrected += 1
        elif task_id in accepted_task_ids:
            mix.accepted += 1
        else:
            mix.unknown += 1

    return mix


async def _correction_rate_by_stage(
    session: SQLModelAsyncSession, project_id: UUID | None
) -> list[StageCorrectionRate]:
    statement = select(
        CorrectionFeedback.task_type,
        CorrectionFeedback.model_value,
        CorrectionFeedback.human_value,
    )
    if project_id is not None:
        statement = statement.where(CorrectionFeedback.project_id == project_id)

    rows = (await session.execute(statement)).all()

    by_stage: dict[str, StageCorrectionRate] = {}
    for task_type, model_value, human_value in rows:
        stage = STAGE_BY_TASK_TYPE.get(task_type, str(task_type))
        entry = by_stage.setdefault(
            stage, StageCorrectionRate(stage=stage, task_types=[])
        )
        if task_type not in entry.task_types:
            entry.task_types.append(task_type)
        entry.feedback_count += 1
        if model_value != human_value:
            entry.corrected_count += 1

    for entry in by_stage.values():
        entry.correction_rate = (
            entry.corrected_count / entry.feedback_count
            if entry.feedback_count
            else None
        )

    return sorted(by_stage.values(), key=lambda e: e.stage)


async def _median_time_to_resolve_hours(
    session: SQLModelAsyncSession, project_id: UUID | None
) -> float | None:
    statement = select(ReviewTask.created_at, ReviewTask.resolved_at).where(
        ReviewTask.status == ReviewStatus.RESOLVED,
        ReviewTask.resolved_at.is_not(None),  # type: ignore[union-attr]
    )
    if project_id is not None:
        statement = statement.where(ReviewTask.project_id == project_id)

    rows = (await session.execute(statement)).all()
    if not rows:
        return None

    durations_hours = [
        (_ensure_aware(resolved_at) - _ensure_aware(created_at)).total_seconds()
        / 3600.0
        for created_at, resolved_at in rows
        if resolved_at is not None
    ]

    return median(durations_hours) if durations_hours else None


async def compute_review_metrics(
    session: SQLModelAsyncSession, project_id: UUID | None = None
) -> ReviewMetricsOut:
    """Queue depth, task age, time-to-resolve, outcome mix, correction rate.

    Scoped to ``project_id`` when given, otherwise across every project --
    an ops dashboard default, not a spoiler-safety boundary (this never
    serves an end user).
    """
    now = datetime.now(UTC)
    open_tasks = await _open_tasks(session, project_id)
    ages = sorted(_age_hours(task.created_at, now) for task in open_tasks)

    age_stats = TaskAgeStats(
        sample_count=len(ages),
        p50_hours=percentile(ages, 0.50),
        p90_hours=percentile(ages, 0.90),
        max_hours=max(ages) if ages else None,
    )

    return ReviewMetricsOut(
        project_id=project_id,
        generated_at=now,
        queue_depth_total=len(open_tasks),
        queue_depth_by_type=await _queue_depth_by_type(session, project_id),
        open_task_age=age_stats,
        median_time_to_resolve_hours=await _median_time_to_resolve_hours(
            session, project_id
        ),
        resolution_outcome_mix=await _resolution_outcome_mix(session, project_id),
        correction_rate_by_stage=await _correction_rate_by_stage(session, project_id),
    )


# LangGraph reserves the checkpoint_writes channels "__interrupt__"/"__resume__"
# (langgraph._internal._constants). A thread's latest checkpoint carrying an
# "__interrupt__" write with no matching "__resume__" write for the same
# task_id is a graph genuinely paused there -- if no OPEN review task points
# at it, a human has nothing to act on and the run can never resume.
_PAUSED_THREADS_SQL = text(
    """
    WITH latest AS (
        SELECT DISTINCT ON (thread_id) thread_id, checkpoint_id
        FROM checkpoints
        ORDER BY thread_id, checkpoint_id DESC
    )
    SELECT DISTINCT cw.thread_id
    FROM checkpoint_writes cw
    JOIN latest l
      ON l.thread_id = cw.thread_id AND l.checkpoint_id = cw.checkpoint_id
    WHERE cw.channel = '__interrupt__'
      AND NOT EXISTS (
          SELECT 1 FROM checkpoint_writes r
          WHERE r.thread_id = cw.thread_id
            AND r.checkpoint_id = cw.checkpoint_id
            AND r.task_id = cw.task_id
            AND r.channel = '__resume__'
      )
    """
)


async def _paused_thread_ids(session: SQLModelAsyncSession) -> set[str]:
    """Thread ids whose latest checkpoint is sitting on an unresumed interrupt.

    Returns an empty set (not an error) if the checkpointer tables don't
    exist yet -- `setup_checkpointer()` runs at deploy time, not import time,
    and a fresh test database legitimately has neither table.
    """
    try:
        rows = (await session.execute(_PAUSED_THREADS_SQL)).all()
    except Exception:
        return set()

    return {row[0] for row in rows}


async def compute_review_alerts(
    session: SQLModelAsyncSession,
    project_id: UUID | None = None,
    queue_depth_threshold: int = DEFAULT_QUEUE_DEPTH_THRESHOLD,
    stale_after_hours: int = STALE_TASK_AGE_HOURS,
) -> ReviewAlertsOut:
    """Queue depth, task age, and orphaned-thread alerts (S7.11).

    ``orphaned_threads`` is project-agnostic -- ``graph_thread_id`` has no
    project column of its own in the checkpointer's tables, so a
    ``project_id`` filter narrows the other two alerts but not this one.
    """
    now = datetime.now(UTC)
    open_tasks = await _open_tasks(session, project_id)
    stale_tasks = [
        StaleTaskOut(
            id=task.id,
            task_type=task.task_type,
            priority=task.priority,
            age_hours=round(_age_hours(task.created_at, now), 2),
        )
        for task in open_tasks
        if _age_hours(task.created_at, now) >= stale_after_hours
    ]
    stale_tasks.sort(key=lambda t: t.age_hours, reverse=True)

    open_thread_ids = {
        task.graph_thread_id for task in open_tasks if task.graph_thread_id
    }
    paused_thread_ids = await _paused_thread_ids(session)
    orphaned_threads = [
        OrphanedThreadOut(
            graph_thread_id=thread_id,
            reason="paused on an interrupt with no open review task",
        )
        for thread_id in sorted(paused_thread_ids - open_thread_ids)
    ]

    queue_depth_total = len(open_tasks)
    queue_depth_breached = queue_depth_total > queue_depth_threshold

    return ReviewAlertsOut(
        project_id=project_id,
        generated_at=now,
        queue_depth_threshold=queue_depth_threshold,
        queue_depth_total=queue_depth_total,
        queue_depth_breached=queue_depth_breached,
        stale_task_threshold_hours=stale_after_hours,
        stale_tasks=stale_tasks,
        orphaned_threads=orphaned_threads,
        has_alerts=queue_depth_breached or bool(stale_tasks) or bool(orphaned_threads),
    )

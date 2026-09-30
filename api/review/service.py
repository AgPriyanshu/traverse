import logging
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import ReviewResolution, ReviewTaskOut
from ..contracts.enums import ReviewStatus, ReviewTaskType
from ..db.models.review_model import ReviewTask
from . import payloads
from . import resolution as resolution_service

logger = logging.getLogger(__name__)


async def _to_out(
    session: SQLModelAsyncSession, task: ReviewTask
) -> ReviewTaskOut | None:
    try:
        payload, score = await payloads.hydrate(session, task)
    except payloads.HydrationError:
        logger.warning("review task %s no longer hydrates; excluding it", task.id)
        return None

    if score != task.priority:
        task.priority = score
        session.add(task)
        await session.commit()

    return ReviewTaskOut(
        id=task.id,
        project_id=task.project_id,
        book_id=task.book_id,
        task_type=task.task_type,
        status=task.status,
        priority=task.priority,
        payload=payload,
        created_at=task.created_at,
    )


async def list_tasks(
    session: SQLModelAsyncSession,
    *,
    project_id: UUID | None,
    task_type: ReviewTaskType | None,
    status: ReviewStatus,
    limit: int,
) -> list[ReviewTaskOut]:
    """Return the queue, blast-radius-first (S7.3).

    Priority is recomputed on read (see ``payloads.hydrate``), so the order
    reflects current state even if the stored ``priority`` column was set at
    queue time against stale data.
    """
    statement = select(ReviewTask).where(ReviewTask.status == status)
    if project_id is not None:
        statement = statement.where(ReviewTask.project_id == project_id)
    if task_type is not None:
        statement = statement.where(ReviewTask.task_type == task_type)

    # Over-fetch a little before the dynamic re-sort: a stored ``priority``
    # that undersells a task (e.g. a mention count that grew since queuing)
    # must not keep it outside the window this query truncates to.
    statement = statement.order_by(ReviewTask.priority.desc())
    statement = statement.limit(max(limit * 3, limit))
    rows = (await session.exec(statement)).all()

    hydrated = [out for row in rows if (out := await _to_out(session, row)) is not None]
    hydrated.sort(key=lambda out: out.priority, reverse=True)

    return hydrated[:limit]


async def resolve_task(
    session: SQLModelAsyncSession, task_id: UUID, body: ReviewResolution
) -> ReviewTaskOut | None:
    """Resolve one task and return its current state, or ``None`` if it does
    not exist.

    Hydrates the payload *before* applying the decision as a fallback: a
    successful ``merge_characters`` resolution deletes one of its own two
    candidates, so re-hydrating strictly after resolving would (correctly)
    fail on referencing a character that is gone. The pre-resolution payload
    is what the reviewer actually acted on and is what the response
    describes; only the ``status``/``resolution`` fields need to reflect the
    outcome.
    """
    task = await session.get(ReviewTask, task_id)
    if task is None:
        return None

    try:
        payload_before, score_before = await payloads.hydrate(session, task)
    except payloads.HydrationError:
        payload_before, score_before = None, task.priority

    resolved = await resolution_service.resolve(session, task, body)

    try:
        payload, score = await payloads.hydrate(session, resolved)
    except payloads.HydrationError:
        if payload_before is None:
            return None
        payload, score = payload_before, score_before

    return ReviewTaskOut(
        id=resolved.id,
        project_id=resolved.project_id,
        book_id=resolved.book_id,
        task_type=resolved.task_type,
        status=resolved.status,
        priority=score,
        payload=payload,
        created_at=resolved.created_at,
    )

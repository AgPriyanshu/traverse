import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.enums import ResolutionMethod, ReviewStatus, ReviewTaskType
from ..db.models import CorrectionFeedback, ReviewTask

logger = logging.getLogger(__name__)


async def _existing_task(
    session: SQLModelAsyncSession,
    *,
    project_id: UUID,
    task_type: ReviewTaskType,
    dedup_key: str,
) -> ReviewTask | None:
    """Return a task already raised for this exact disagreement, open or resolved.

    Keyed on a ``dedup_key`` the caller embeds in ``payload`` (Pydantic drops
    it on the way out through the frozen ``ReviewTaskPayload`` union, since
    none of the six shapes declares it -- it never reaches a renderer, it only
    ever reaches this query). An **open** match means a rerun reproduced a
    disagreement the queue has not answered yet: don't queue it twice. A
    **resolved** match means a human already ruled on this exact pair or
    field: re-raising it on every subsequent rerun would be exactly the
    "reviewer stops reviewing" failure S7.5's mission statement warns about.
    """
    statement = select(ReviewTask).where(
        ReviewTask.project_id == project_id,
        ReviewTask.task_type == task_type,
        ReviewTask.payload["dedup_key"].astext == dedup_key,  # type: ignore[index]
    )
    return (await session.execute(statement)).scalars().first()


async def raise_disagreement(
    session: SQLModelAsyncSession,
    *,
    project_id: UUID,
    book_id: UUID | None,
    task_type: ReviewTaskType,
    dedup_key: str,
    payload: dict[str, Any],
    priority: int = 1,
) -> ReviewTask | None:
    """Queue a review task for a rerun disagreement, exactly once per ``dedup_key``.

    Returns the new task, or ``None`` if a matching task (open or already
    resolved) exists and nothing was written -- the caller does not need its
    own existence check before calling this.

    Args:
        session: Open session; this function commits.
        project_id: Owning project.
        book_id: Book the disagreement surfaced in, if any.
        task_type: One of the six frozen ``ReviewTaskType`` values. The
            payload dict must already match that type's contract shape
            (``api/contracts/api.py``, "Sprint 7 (S7.2)") plus ``dedup_key``.
        dedup_key: A stable string identifying *this* disagreement (e.g.
            ``f"chapter:{chapter_id}"`` or the sorted pair of two character
            ids) -- stable across reruns of the same underlying conflict,
            distinct across genuinely different ones.
        payload: The task's payload, contract-shaped; ``dedup_key`` is added
            to it here so a caller does not have to remember to.
        priority: Blast radius, per S7.3's ordering -- callers pass their own.
    """
    existing = await _existing_task(
        session, project_id=project_id, task_type=task_type, dedup_key=dedup_key
    )
    if existing is not None:
        return None

    task = ReviewTask(
        project_id=project_id,
        book_id=book_id,
        task_type=task_type,
        payload={**payload, "dedup_key": dedup_key},
        priority=priority,
        status=ReviewStatus.OPEN,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    return task


async def record_correction_feedback(
    session: SQLModelAsyncSession,
    *,
    project_id: UUID,
    task_type: ReviewTaskType,
    model_value: dict[str, Any],
    human_value: dict[str, Any],
    model_confidence: float | None,
    review_task_id: UUID | None = None,
    resolution_method: ResolutionMethod = ResolutionMethod.HUMAN,
    evidence: dict[str, Any] | None = None,
) -> CorrectionFeedback:
    """Persist one correction with everything Sprint 8's calibrator needs (S7.7).

    ``model_confidence`` must be the value the model reported when the
    disagreement was first raised -- read it back out of the resolved task's
    ``payload`` (every ``raise_disagreement`` caller in this codebase stores
    it there under a type-specific key, since none of the frozen payload
    shapes carries a generic ``model_confidence`` field). It cannot be
    recomputed after the fact: the model that produced it may have already
    been re-routed or re-prompted by the time a human answers.

    Called by a review task's resolution handler (``api/review/**``, S7.2) at
    the moment a human answers -- not by the code that raises the task, which
    has no human decision yet to record.
    """
    feedback = CorrectionFeedback(
        project_id=project_id,
        review_task_id=review_task_id,
        task_type=task_type,
        model_value=model_value,
        human_value=human_value,
        model_confidence=model_confidence,
        resolution_method=resolution_method,
        evidence=evidence,
    )
    session.add(feedback)
    await session.commit()
    await session.refresh(feedback)

    return feedback


async def list_correction_feedback(
    session: SQLModelAsyncSession,
    *,
    project_id: UUID | None = None,
    task_type: ReviewTaskType | None = None,
) -> list[CorrectionFeedback]:
    """Return correction feedback rows for Sprint 8's calibrator, optionally scoped."""
    statement = select(CorrectionFeedback)

    if project_id is not None:
        statement = statement.where(CorrectionFeedback.project_id == project_id)
    if task_type is not None:
        statement = statement.where(CorrectionFeedback.task_type == task_type)

    return list((await session.execute(statement)).scalars().all())

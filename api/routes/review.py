from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import ReviewResolution, ReviewTaskOut
from ..contracts.enums import ReviewStatus, ReviewTaskType
from ..db.engine import get_session
from ..review import service

router = APIRouter(tags=["review"])
OWNER = "be2"


@router.get("/review/tasks", response_model=list[ReviewTaskOut])
async def list_tasks(
    project_id: UUID | None = Query(default=None),
    task_type: ReviewTaskType | None = Query(default=None),
    status: ReviewStatus = Query(default=ReviewStatus.OPEN),
    limit: int = Query(default=50, le=200),
    session: SQLModelAsyncSession = Depends(get_session),
) -> list[ReviewTaskOut]:
    """Return the queue, highest blast radius first (S7.3)."""
    return await service.list_tasks(
        session, project_id=project_id, task_type=task_type, status=status, limit=limit
    )


@router.post("/review/tasks/{task_id}/resolve", response_model=ReviewTaskOut)
async def resolve_task(
    task_id: UUID,
    body: ReviewResolution,
    session: SQLModelAsyncSession = Depends(get_session),
) -> ReviewTaskOut:
    """Apply a decision and resume whatever it was blocking (S7.2, S7.4).

    Idempotent: resolving an already-resolved task returns its current state
    rather than erroring or re-applying the decision.
    """
    result = await service.resolve_task(session, task_id, body)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "review task not found")

    return result

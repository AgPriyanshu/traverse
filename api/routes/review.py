"""The human review queue. Owned by backend engineer 2."""

from uuid import UUID

from fastapi import APIRouter, Query

from ..contracts.api import ReviewResolution, ReviewTaskOut
from ..contracts.enums import ReviewStatus, ReviewTaskType
from ._stub import not_implemented

router = APIRouter(tags=["review"])
OWNER = "be2"


@router.get("/review/tasks", response_model=list[ReviewTaskOut])
async def list_tasks(
    project_id: UUID | None = Query(default=None),
    task_type: ReviewTaskType | None = Query(default=None),
    status: ReviewStatus = Query(default=ReviewStatus.OPEN),
    limit: int = Query(default=50, le=200),
) -> list[ReviewTaskOut]:
    not_implemented(OWNER, "S7.2")


@router.post("/review/tasks/{task_id}/resolve", response_model=ReviewTaskOut)
async def resolve_task(task_id: UUID, body: ReviewResolution) -> ReviewTaskOut:
    not_implemented(OWNER, "S7.4")

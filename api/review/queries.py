from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.enums import ReviewStatus, ReviewTaskType
from ..db.models.review_model import ReviewTask


async def open_blocking_task_ids(
    session: SQLModelAsyncSession,
    *,
    book_id: UUID,
    task_types: tuple[ReviewTaskType, ...],
) -> list[str]:
    """Return the ids of this book's OPEN tasks of the given types.

    Scoped to ``book_id``, not ``project_id``: a cross-book merge queued
    against a *different* book in the same series must not block this book's
    own pipeline run indefinitely — only ambiguity about *this* book's own
    roster or edges gates *this* book's stages.
    """
    rows = (
        await session.exec(
            select(ReviewTask.id)
            .where(ReviewTask.book_id == book_id)
            .where(ReviewTask.task_type.in_(task_types))
            .where(ReviewTask.status == ReviewStatus.OPEN)
        )
    ).all()

    return [str(row) for row in rows]

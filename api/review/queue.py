from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import MentionOut
from ..contracts.enums import CandidateKind, ReviewTaskType
from ..db.models.review_model import ReviewTask
from . import priority as priority_scoring


async def queue_classify_candidate(
    session: SQLModelAsyncSession,
    *,
    project_id: UUID,
    book_id: UUID,
    candidate_id: UUID,
    surface_form: str,
    kind_guess: CandidateKind | None,
    mention_count: int,
    contexts: list[MentionOut],
) -> ReviewTask:
    """Queue a ``classify_candidate`` task. Commits."""
    task = ReviewTask(
        project_id=project_id,
        book_id=book_id,
        task_type=ReviewTaskType.CLASSIFY_CANDIDATE,
        payload={
            "candidate_id": str(candidate_id),
            "surface_form": surface_form,
            "book_id": str(book_id),
            "kind_guess": kind_guess.value if kind_guess else None,
            "mention_count": mention_count,
            "contexts": [c.model_dump(mode="json") for c in contexts],
        },
        priority=priority_scoring.blast_radius(
            task_type=ReviewTaskType.CLASSIFY_CANDIDATE,
            max_tier=None,
            cascade=mention_count,
        ),
    )
    session.add(task)
    await session.commit()

    return task


async def queue_confirm_chapter_split(
    session: SQLModelAsyncSession,
    *,
    project_id: UUID,
    book_id: UUID,
    chapter_id: UUID,
    chapter: dict,
    preceding_text: str,
    following_text: str,
    confidence: float | None,
) -> ReviewTask:
    """Queue a ``confirm_chapter_split`` task. Commits.

    Args:
        chapter: A ``ChapterOut``-shaped dict — pass
            ``chapter_out.model_dump(mode="json")``.
    """
    task = ReviewTask(
        project_id=project_id,
        book_id=book_id,
        task_type=ReviewTaskType.CONFIRM_CHAPTER_SPLIT,
        payload={
            "chapter_id": str(chapter_id),
            "chapter": chapter,
            "preceding_text": preceding_text,
            "following_text": following_text,
            "confidence": confidence,
        },
        priority=priority_scoring.blast_radius(
            task_type=ReviewTaskType.CONFIRM_CHAPTER_SPLIT, max_tier=None
        ),
    )
    session.add(task)
    await session.commit()

    return task

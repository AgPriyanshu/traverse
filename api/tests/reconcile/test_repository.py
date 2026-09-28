from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import ReviewTaskType
from api.db.models import Character, Project
from api.db.models.review_model import ReviewTask
from api.reconcile import repository

from .conftest import make_book


async def _character(
    session: SQLModelAsyncSession, project: Project, name: str
) -> Character:
    character = Character(project_id=project.id, canonical_name=name)
    session.add(character)
    await session.commit()
    await session.refresh(character)

    return character


class TestQueueCrossBookReview:
    async def test_writes_a_contract_shaped_payload(
        self, session: SQLModelAsyncSession, series_project: Project
    ) -> None:
        book2 = await make_book(session, series_project, series_order=2)
        candidate = await _character(session, series_project, "Old Matthew")
        target = await _character(session, series_project, "Matthew Cuthbert")

        await repository.queue_cross_book_review(
            session,
            project_id=series_project.id,
            book_id=book2.id,
            candidate=candidate,
            target=target,
            reason="character_death",
            confidence=0.4,
        )

        tasks = (
            (
                await session.execute(
                    select(ReviewTask).where(
                        ReviewTask.task_type == ReviewTaskType.MERGE_ACROSS_BOOKS
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(tasks) == 1
        candidate_names = {c["canonical_name"] for c in tasks[0].payload["candidates"]}
        assert candidate_names == {"Old Matthew", "Matthew Cuthbert"}
        assert tasks[0].payload["similarity_score"] == 0.4

    async def test_a_reproduced_block_does_not_requeue(
        self, session: SQLModelAsyncSession, series_project: Project
    ) -> None:
        book2 = await make_book(session, series_project, series_order=2)
        candidate = await _character(session, series_project, "Old Matthew")
        target = await _character(session, series_project, "Matthew Cuthbert")

        for _ in range(2):
            await repository.queue_cross_book_review(
                session,
                project_id=series_project.id,
                book_id=book2.id,
                candidate=candidate,
                target=target,
                reason="character_death",
                confidence=0.4,
            )

        tasks = (
            (
                await session.execute(
                    select(ReviewTask).where(
                        ReviewTask.task_type == ReviewTaskType.MERGE_ACROSS_BOOKS
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(tasks) == 1

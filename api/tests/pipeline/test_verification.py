from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import ReviewStatus, ReviewTaskType
from api.db.models import Book, Project
from api.pipeline import verification


class TestRaiseDisagreement:
    async def test_creates_a_task_with_the_dedup_key_embedded(
        self, session: SQLModelAsyncSession, project: Project, book: Book
    ) -> None:
        task = await verification.raise_disagreement(
            session,
            project_id=project.id,
            book_id=book.id,
            task_type=ReviewTaskType.CONFIRM_CHAPTER_SPLIT,
            dedup_key="chapter:1",
            payload={
                "chapter": {"id": str(book.id)},
                "preceding_text": "a",
                "following_text": "b",
            },
        )

        assert task is not None
        assert task.payload["dedup_key"] == "chapter:1"
        assert task.status == ReviewStatus.OPEN

    async def test_a_second_call_with_the_same_dedup_key_is_a_no_op(
        self, session: SQLModelAsyncSession, project: Project, book: Book
    ) -> None:
        kwargs = dict(
            project_id=project.id,
            book_id=book.id,
            task_type=ReviewTaskType.CONFIRM_CHAPTER_SPLIT,
            dedup_key="chapter:1",
            payload={"chapter": {}, "preceding_text": "a", "following_text": "b"},
        )
        first = await verification.raise_disagreement(session, **kwargs)
        second = await verification.raise_disagreement(session, **kwargs)

        assert first is not None
        assert second is None

    async def test_a_resolved_task_is_not_reraised(
        self, session: SQLModelAsyncSession, project: Project, book: Book
    ) -> None:
        task = await verification.raise_disagreement(
            session,
            project_id=project.id,
            book_id=book.id,
            task_type=ReviewTaskType.CONFIRM_CHAPTER_SPLIT,
            dedup_key="chapter:1",
            payload={"chapter": {}, "preceding_text": "a", "following_text": "b"},
        )
        assert task is not None
        task.status = ReviewStatus.RESOLVED
        session.add(task)
        await session.commit()

        again = await verification.raise_disagreement(
            session,
            project_id=project.id,
            book_id=book.id,
            task_type=ReviewTaskType.CONFIRM_CHAPTER_SPLIT,
            dedup_key="chapter:1",
            payload={"chapter": {}, "preceding_text": "a", "following_text": "c"},
        )
        assert again is None

    async def test_a_different_dedup_key_is_a_genuinely_new_task(
        self, session: SQLModelAsyncSession, project: Project, book: Book
    ) -> None:
        first = await verification.raise_disagreement(
            session,
            project_id=project.id,
            book_id=book.id,
            task_type=ReviewTaskType.CONFIRM_CHAPTER_SPLIT,
            dedup_key="chapter:1",
            payload={"chapter": {}, "preceding_text": "a", "following_text": "b"},
        )
        second = await verification.raise_disagreement(
            session,
            project_id=project.id,
            book_id=book.id,
            task_type=ReviewTaskType.CONFIRM_CHAPTER_SPLIT,
            dedup_key="chapter:2",
            payload={"chapter": {}, "preceding_text": "a", "following_text": "b"},
        )

        assert first is not None
        assert second is not None
        assert first.id != second.id


class TestCorrectionFeedback:
    async def test_records_decision_time_confidence(
        self, session: SQLModelAsyncSession, project: Project
    ) -> None:
        feedback = await verification.record_correction_feedback(
            session,
            project_id=project.id,
            task_type=ReviewTaskType.CONFIRM_CHAPTER_SPLIT,
            model_value={"title": "Re-detected Title"},
            human_value={"title": "Verified Title"},
            model_confidence=0.42,
        )

        assert feedback.id is not None
        assert feedback.model_confidence == 0.42

        rows = await verification.list_correction_feedback(
            session, project_id=project.id
        )
        assert len(rows) == 1
        assert rows[0].model_value == {"title": "Re-detected Title"}
        assert rows[0].human_value == {"title": "Verified Title"}

    async def test_list_can_scope_by_task_type(
        self, session: SQLModelAsyncSession, project: Project
    ) -> None:
        await verification.record_correction_feedback(
            session,
            project_id=project.id,
            task_type=ReviewTaskType.CONFIRM_CHAPTER_SPLIT,
            model_value={},
            human_value={},
            model_confidence=0.5,
        )
        await verification.record_correction_feedback(
            session,
            project_id=project.id,
            task_type=ReviewTaskType.CLASSIFY_CANDIDATE,
            model_value={},
            human_value={},
            model_confidence=0.6,
        )

        rows = await verification.list_correction_feedback(
            session, project_id=project.id, task_type=ReviewTaskType.CLASSIFY_CANDIDATE
        )
        assert len(rows) == 1
        assert rows[0].task_type == ReviewTaskType.CLASSIFY_CANDIDATE

import uuid
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import ReviewStatus, ReviewTaskType
from api.db.models import Book, CorrectionFeedback, Project, ReviewTask
from api.graph.checkpoint import setup_checkpointer
from api.ops.review_metrics import compute_review_alerts, compute_review_metrics


def _task(
    project: Project,
    book: Book,
    *,
    task_type: ReviewTaskType = ReviewTaskType.CLASSIFY_CANDIDATE,
    status: ReviewStatus = ReviewStatus.OPEN,
    priority: int = 0,
    created_at: datetime | None = None,
    resolved_at: datetime | None = None,
    graph_thread_id: str | None = None,
) -> ReviewTask:
    return ReviewTask(
        project_id=project.id,
        book_id=book.id,
        task_type=task_type,
        payload={},
        status=status,
        priority=priority,
        created_at=created_at or datetime.now(UTC),
        resolved_at=resolved_at,
        graph_thread_id=graph_thread_id,
    )


async def test_queue_depth_counts_only_open_tasks(
    session: SQLModelAsyncSession, project: Project, book: Book
) -> None:
    session.add_all(
        [
            _task(project, book, task_type=ReviewTaskType.CLASSIFY_CANDIDATE),
            _task(project, book, task_type=ReviewTaskType.CLASSIFY_CANDIDATE),
            _task(
                project,
                book,
                task_type=ReviewTaskType.CONFIRM_RELATION,
                status=ReviewStatus.RESOLVED,
                resolved_at=datetime.now(UTC),
            ),
            _task(project, book, status=ReviewStatus.DISMISSED),
        ]
    )
    await session.commit()

    out = await compute_review_metrics(session, project_id=project.id)

    assert out.queue_depth_total == 2
    by_type = {row.task_type: row.open_count for row in out.queue_depth_by_type}
    assert by_type == {ReviewTaskType.CLASSIFY_CANDIDATE: 2}


async def test_open_task_age_reports_percentiles(
    session: SQLModelAsyncSession, project: Project, book: Book
) -> None:
    now = datetime.now(UTC)
    session.add_all(
        [
            _task(project, book, created_at=now - timedelta(hours=1)),
            _task(project, book, created_at=now - timedelta(hours=10)),
            _task(project, book, created_at=now - timedelta(hours=100)),
        ]
    )
    await session.commit()

    out = await compute_review_metrics(session, project_id=project.id)

    assert out.open_task_age.sample_count == 3
    assert out.open_task_age.max_hours is not None
    assert out.open_task_age.max_hours >= 99.9
    assert out.open_task_age.p50_hours is not None


async def test_median_time_to_resolve_only_counts_resolved(
    session: SQLModelAsyncSession, project: Project, book: Book
) -> None:
    now = datetime.now(UTC)
    session.add_all(
        [
            _task(
                project,
                book,
                status=ReviewStatus.RESOLVED,
                created_at=now - timedelta(hours=4),
                resolved_at=now,
            ),
            _task(
                project,
                book,
                status=ReviewStatus.RESOLVED,
                created_at=now - timedelta(hours=2),
                resolved_at=now,
            ),
            _task(project, book, status=ReviewStatus.OPEN, created_at=now),
        ]
    )
    await session.commit()

    out = await compute_review_metrics(session, project_id=project.id)

    assert out.median_time_to_resolve_hours == 3.0


async def test_resolution_outcome_mix_from_correction_feedback(
    session: SQLModelAsyncSession, project: Project, book: Book
) -> None:
    accepted_task = _task(project, book, status=ReviewStatus.RESOLVED)
    corrected_task = _task(project, book, status=ReviewStatus.RESOLVED)
    unknown_task = _task(project, book, status=ReviewStatus.RESOLVED)
    dismissed_task = _task(project, book, status=ReviewStatus.DISMISSED)
    session.add_all([accepted_task, corrected_task, unknown_task, dismissed_task])
    await session.commit()
    for task in (accepted_task, corrected_task, unknown_task):
        await session.refresh(task)

    session.add_all(
        [
            CorrectionFeedback(
                project_id=project.id,
                review_task_id=accepted_task.id,
                task_type=accepted_task.task_type,
                model_value={"name": "Jane"},
                human_value={"name": "Jane"},
            ),
            CorrectionFeedback(
                project_id=project.id,
                review_task_id=corrected_task.id,
                task_type=corrected_task.task_type,
                model_value={"name": "Jane"},
                human_value={"name": "Jane Bennet"},
            ),
        ]
    )
    await session.commit()

    out = await compute_review_metrics(session, project_id=project.id)

    assert out.resolution_outcome_mix.accepted == 1
    assert out.resolution_outcome_mix.corrected == 1
    assert out.resolution_outcome_mix.unknown == 1
    assert out.resolution_outcome_mix.rejected == 1


async def test_correction_rate_groups_by_stage_not_task_type(
    session: SQLModelAsyncSession, project: Project, book: Book
) -> None:
    session.add_all(
        [
            CorrectionFeedback(
                project_id=project.id,
                task_type=ReviewTaskType.CONFIRM_RELATION,
                model_value={"predicate": "sibling"},
                human_value={"predicate": "spouse"},
            ),
            CorrectionFeedback(
                project_id=project.id,
                task_type=ReviewTaskType.RESOLVE_CONFLICT,
                model_value={"predicate": "spouse"},
                human_value={"predicate": "spouse"},
            ),
        ]
    )
    await session.commit()

    out = await compute_review_metrics(session, project_id=project.id)

    stage = next(
        row
        for row in out.correction_rate_by_stage
        if row.stage == "pass2_relation_extraction"
    )
    assert stage.feedback_count == 2
    assert stage.corrected_count == 1
    assert stage.correction_rate == 0.5
    assert set(stage.task_types) == {
        ReviewTaskType.CONFIRM_RELATION,
        ReviewTaskType.RESOLVE_CONFLICT,
    }


async def test_alerts_flag_queue_depth_breach(
    session: SQLModelAsyncSession, project: Project, book: Book
) -> None:
    session.add_all([_task(project, book) for _ in range(3)])
    await session.commit()

    out = await compute_review_alerts(
        session, project_id=project.id, queue_depth_threshold=2
    )

    assert out.queue_depth_breached is True
    assert out.has_alerts is True


async def test_alerts_flag_stale_tasks(
    session: SQLModelAsyncSession, project: Project, book: Book
) -> None:
    now = datetime.now(UTC)
    session.add_all(
        [
            _task(project, book, created_at=now - timedelta(hours=49)),
            _task(project, book, created_at=now - timedelta(hours=1)),
        ]
    )
    await session.commit()

    out = await compute_review_alerts(
        session, project_id=project.id, queue_depth_threshold=100
    )

    assert len(out.stale_tasks) == 1
    assert out.stale_tasks[0].age_hours >= 48


class _CheckpointRows:
    """Minimal direct inserts into LangGraph's own tables to simulate a paused thread.

    Cheaper than driving a real graph through an interrupt for a unit test, and
    exercises exactly the columns ``review_metrics._paused_thread_ids`` reads.
    """

    def __init__(self, session: SQLModelAsyncSession) -> None:
        self.session = session
        self.thread_ids: list[str] = []

    async def paused(self, thread_id: str) -> None:
        await self._checkpoint(thread_id)
        await self._write(thread_id, task_id="t1", channel="__interrupt__")

    async def resumed(self, thread_id: str) -> None:
        await self._checkpoint(thread_id)
        await self._write(thread_id, task_id="t1", channel="__interrupt__")
        await self._write(thread_id, task_id="t1", channel="__resume__", idx=1)

    async def _checkpoint(self, thread_id: str) -> None:
        self.thread_ids.append(thread_id)
        await self.session.execute(
            text(
                "INSERT INTO checkpoints "
                "(thread_id, checkpoint_ns, checkpoint_id, checkpoint, metadata) "
                "VALUES (:thread_id, '', :checkpoint_id, '{}'::jsonb, '{}'::jsonb)"
            ),
            {"thread_id": thread_id, "checkpoint_id": "0001"},
        )

    async def _write(
        self, thread_id: str, *, task_id: str, channel: str, idx: int = 0
    ) -> None:
        await self.session.execute(
            text(
                "INSERT INTO checkpoint_writes "
                "(thread_id, checkpoint_ns, checkpoint_id, task_id, "
                "idx, channel, type, blob) "
                "VALUES (:thread_id, '', '0001', :task_id, :idx, :channel, "
                "'msgpack', '\\x00'::bytea)"
            ),
            {
                "thread_id": thread_id,
                "task_id": task_id,
                "idx": idx,
                "channel": channel,
            },
        )

    async def cleanup(self) -> None:
        for thread_id in self.thread_ids:
            await self.session.execute(
                text("DELETE FROM checkpoint_writes WHERE thread_id = :t"),
                {"t": thread_id},
            )
            await self.session.execute(
                text("DELETE FROM checkpoints WHERE thread_id = :t"),
                {"t": thread_id},
            )
        await self.session.commit()


@pytest_asyncio.fixture
async def checkpoint_rows(session: SQLModelAsyncSession):
    await setup_checkpointer()
    rows = _CheckpointRows(session)
    yield rows
    await rows.cleanup()


async def test_orphaned_thread_flagged_without_an_open_task(
    session: SQLModelAsyncSession,
    project: Project,
    book: Book,
    checkpoint_rows: _CheckpointRows,
) -> None:
    orphan_thread = f"orphan-{uuid.uuid4()}"
    covered_thread = f"covered-{uuid.uuid4()}"
    resumed_thread = f"resumed-{uuid.uuid4()}"
    await checkpoint_rows.paused(orphan_thread)
    await checkpoint_rows.paused(covered_thread)
    await checkpoint_rows.resumed(resumed_thread)

    session.add(_task(project, book, graph_thread_id=covered_thread))
    await session.commit()

    out = await compute_review_alerts(session, project_id=project.id)

    flagged = {row.graph_thread_id for row in out.orphaned_threads}
    assert orphan_thread in flagged
    assert covered_thread not in flagged
    assert resumed_thread not in flagged

"""S7.4 acceptance: interrupt, kill, restart, resume, complete -- under
concurrent load. Sprint 1 already proved the single-thread version
(``api/tests/graph/test_checkpointer.py``, a real SIGKILLed subprocess); this
sprint's addition is what only shows up under contention: a double-click on
one task must resolve it exactly once, and many books paused at once must
each resume independently after a restart with no cross-thread bleed.

"Restart" is simulated at the checkpointer level, as the brief allows: every
call below opens its own fresh ``AsyncPostgresSaver`` (via ``checkpointer()``)
and its own fresh ``AsyncSession``, so nothing carries over between calls
except what actually committed to Postgres -- the same substitution
``checkpoint_probe.py`` makes for "a different process" when it re-invokes a
second ``build_graph(saver)`` after a real kill.
"""

import asyncio
import uuid

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.api import ReviewResolution
from api.contracts.enums import ReviewStatus, ReviewTaskType
from api.db.engine import engine
from api.db.models import Book, Character
from api.db.models.review_model import CorrectionFeedback, ReviewTask
from api.review import resolution, workflow


async def _character(session, project, name: str) -> Character:
    character = Character(project_id=project.id, canonical_name=name)
    session.add(character)
    await session.commit()
    await session.refresh(character)

    return character


@pytest.mark.asyncio
async def test_concurrent_double_click_resolves_the_merge_exactly_once(
    session, project, book
):
    target = await _character(session, project, "Catherine Earnshaw")
    source = await _character(session, project, "Catherine (dup)")
    task = ReviewTask(
        project_id=project.id,
        book_id=book.id,
        task_type=ReviewTaskType.MERGE_CHARACTERS,
        payload={"name_a": target.canonical_name, "name_b": source.canonical_name},
        priority=1,
    )
    session.add(task)
    await session.commit()
    task_id = task.id

    body = ReviewResolution(
        decision="merge",
        payload={"primary_id": str(target.id), "merge_ids": [str(source.id)]},
    )

    async def _attempt():
        async with SQLModelAsyncSession(engine, expire_on_commit=False) as own_session:
            own_task = await own_session.get(ReviewTask, task_id)

            return await resolution.resolve(own_session, own_task, body)

    results = await asyncio.gather(_attempt(), _attempt(), _attempt())

    assert all(r.status == ReviewStatus.RESOLVED for r in results)

    async with SQLModelAsyncSession(engine, expire_on_commit=False) as check:
        assert await check.get(Character, source.id) is None
        survivor = await check.get(Character, target.id)
        assert survivor is not None
        assert survivor.human_verified is True

        feedback = (
            await check.exec(
                select(CorrectionFeedback).where(
                    CorrectionFeedback.review_task_id == task_id
                )
            )
        ).all()
        # Exactly one caller's handler ran; the other two saw rowcount == 0
        # and returned the already-resolved row without touching the graph.
        assert len(feedback) == 1


@pytest.mark.asyncio
async def test_many_books_paused_at_once_each_resume_independently_after_restart(
    session, project
):
    books: list[Book] = []
    for i in range(6):
        row = Book(
            project_id=project.id,
            title=f"Restart Book {i}",
            content_hash=uuid.uuid4().hex,
        )
        session.add(row)
        books.append(row)
    await session.commit()
    for row in books:
        await session.refresh(row)

    tasks: list[ReviewTask] = []
    for row in books:
        task = ReviewTask(
            project_id=project.id,
            book_id=row.id,
            task_type=ReviewTaskType.MERGE_CHARACTERS,
            payload={"name_a": f"A-{row.id}", "name_b": f"B-{row.id}"},
            priority=1,
        )
        session.add(task)
        tasks.append(task)
    await session.commit()
    for task in tasks:
        await session.refresh(task)

    # Pause every book's roster gate concurrently: one interrupt each,
    # checkpointed to Postgres independently.
    paused = await asyncio.gather(
        *(workflow.pass_gate(row.id, workflow.ROSTER_GATE) for row in books)
    )
    assert paused == [False] * len(books)

    async def _resolve(task: ReviewTask) -> ReviewTask:
        async with SQLModelAsyncSession(engine, expire_on_commit=False) as own_session:
            own_task = await own_session.get(ReviewTask, task.id)

            return await resolution.resolve(
                own_session, own_task, ReviewResolution(decision="keep_separate")
            )

    resolved = await asyncio.gather(*(_resolve(task) for task in tasks))
    assert all(t.status == ReviewStatus.RESOLVED for t in resolved)

    # ``resolution.resolve`` already resumed each gate itself
    # (``_maybe_resume_pipeline``) -- confirm the transition already
    # happened via ``gate_state`` rather than resuming a second time (a
    # gate with nothing left to clear correctly reports no transition, so
    # calling ``resume_gate`` again here would just prove that, not this).

    # No cross-thread bleed: every book's own gate cleared, and clearing one
    # book's thread did not silently clear (or re-pause) another's.
    states = await asyncio.gather(
        *(workflow.gate_state(row.id, workflow.ROSTER_GATE) for row in books)
    )
    assert all(is_paused is False for is_paused, _blocking in states)

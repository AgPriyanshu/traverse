import pytest

from api.contracts.enums import ReviewStatus, ReviewTaskType
from api.db.models.review_model import ReviewTask
from api.review import workflow


@pytest.mark.asyncio
async def test_pass_gate_clears_when_nothing_is_open(book):
    assert await workflow.pass_gate(book.id, workflow.ROSTER_GATE) is True


@pytest.mark.asyncio
async def test_pass_gate_interrupts_when_a_task_is_open(session, project, book):
    task = ReviewTask(
        project_id=project.id,
        book_id=book.id,
        task_type=ReviewTaskType.MERGE_CHARACTERS,
        payload={"name_a": "A", "name_b": "B"},
        priority=1,
    )
    session.add(task)
    await session.commit()

    assert await workflow.pass_gate(book.id, workflow.ROSTER_GATE) is False

    paused, blocking = await workflow.gate_state(book.id, workflow.ROSTER_GATE)
    assert paused is True
    assert str(task.id) in blocking


@pytest.mark.asyncio
async def test_resume_gate_clears_only_after_the_task_resolves(session, project, book):
    task = ReviewTask(
        project_id=project.id,
        book_id=book.id,
        task_type=ReviewTaskType.MERGE_CHARACTERS,
        payload={"name_a": "A", "name_b": "B"},
        priority=1,
    )
    session.add(task)
    await session.commit()

    assert await workflow.pass_gate(book.id, workflow.ROSTER_GATE) is False

    # Resolving nothing yet -- still open, resuming must not clear the gate.
    assert await workflow.resume_gate(book.id, workflow.ROSTER_GATE) is False

    task.status = ReviewStatus.RESOLVED
    session.add(task)
    await session.commit()

    assert await workflow.resume_gate(book.id, workflow.ROSTER_GATE) is True
    # A second resume on an already-clear gate is a no-op, not a fresh clear.
    assert await workflow.resume_gate(book.id, workflow.ROSTER_GATE) is False


@pytest.mark.asyncio
async def test_resume_gate_on_a_never_paused_thread_is_false(book):
    assert await workflow.resume_gate(book.id, workflow.CONFLICT_GATE) is False


@pytest.mark.asyncio
async def test_roster_and_conflict_gates_are_independent(session, project, book):
    """The two gates for one book must not share a thread -- an open
    ``resolve_conflict`` task must not block pass 2 from ever starting, and an
    open ``merge_characters`` task must not block a Neo4j projection that
    never needed to wait on it."""
    session.add(
        ReviewTask(
            project_id=project.id,
            book_id=book.id,
            task_type=ReviewTaskType.RESOLVE_CONFLICT,
            payload={
                "type": "incompatible_relations",
                "character_ids": [],
                "relations": [],
            },
            priority=10,
        )
    )
    await session.commit()

    assert await workflow.pass_gate(book.id, workflow.CONFLICT_GATE) is False
    assert await workflow.pass_gate(book.id, workflow.ROSTER_GATE) is True

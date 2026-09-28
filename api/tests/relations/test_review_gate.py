"""S7.1: the frozen chain must defer, not fail, when a stage's gate is open.

``relations.extract``/``relations.aggregate`` both check the ``roster`` gate
(``api/review/workflow.py``) before doing any work; ``graph.upsert`` checks
both gates. This pins that a blocked book returns quietly (no exception, no
side effect) rather than dead-lettering on a pending human decision.
"""

import uuid

import pytest

from api.contracts.enums import ReviewTaskType, StageName
from api.db.models.review_model import ReviewTask
from api.graph.tasks import _upsert_graph
from api.relations.tasks import _aggregate_relations, _extract_relations
from api.workers.stages import StageRecord


def _fake_record(stage_name: StageName) -> StageRecord:
    return StageRecord(
        run_id=uuid.uuid4(), stage_id=uuid.uuid4(), stage=stage_name, attempt=1
    )


@pytest.mark.asyncio
async def test_extract_relations_defers_while_roster_is_ambiguous(
    session, project, book
):
    session.add(
        ReviewTask(
            project_id=project.id,
            book_id=book.id,
            task_type=ReviewTaskType.MERGE_CHARACTERS,
            payload={"name_a": "A", "name_b": "B"},
            priority=1,
        )
    )
    await session.commit()

    record = _fake_record(StageName.EXTRACT_RELATIONS)
    await _extract_relations(book.id, record)

    assert record.rows_written is None


@pytest.mark.asyncio
async def test_aggregate_relations_defers_while_roster_is_ambiguous(
    session, project, book
):
    session.add(
        ReviewTask(
            project_id=project.id,
            book_id=book.id,
            task_type=ReviewTaskType.MERGE_ACROSS_BOOKS,
            payload={
                "candidate_name": "A",
                "target_name": "B",
                "target_character_id": str(uuid.uuid4()),
                "reason": "x",
                "confidence": 0.5,
            },
            priority=2,
        )
    )
    await session.commit()

    record = _fake_record(StageName.AGGREGATE_RELATIONS)
    # No staged artifact exists either -- the gate must short-circuit before
    # the "relations.extract must run first" PermanentError would fire.
    await _aggregate_relations(book.id, record)

    assert record.rows_written is None


@pytest.mark.asyncio
async def test_upsert_graph_defers_while_either_gate_is_open(session, project, book):
    session.add(
        ReviewTask(
            project_id=project.id,
            book_id=book.id,
            task_type=ReviewTaskType.MERGE_CHARACTERS,
            payload={"name_a": "A", "name_b": "B"},
            priority=1,
        )
    )
    await session.commit()

    result = await _upsert_graph(book.id)

    assert result["deferred"] is True

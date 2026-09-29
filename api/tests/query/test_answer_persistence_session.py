import json

import pytest
from httpx import AsyncClient

from api.contracts.api import QueryRequest
from api.contracts.enums import QueryRoute
from api.db.models import Project
from api.query import router
from api.query.router import RouterOutput


@pytest.mark.asyncio
async def test_query_route_persists_the_answer_without_a_greenlet_error(
    client: AsyncClient, project: Project, monkeypatch
):
    """Regression test for a real bug (Sprint 8 retro, do1): the request-scoped
    session (``api/db/engine.py::get_session``, ``expire_on_commit=True`` by
    default) is committed against three times inside ``_finish`` --
    ``write_query_log``, ``record_turn``, ``set_scope`` -- and a later
    synchronous read of an expired ``Conversation`` attribute used to raise
    ``greenlet_spawn has not been called`` on every single query, right after
    the answer itself had already been correctly produced.

    Only the real HTTP route reproduces this: ``api/tests/conftest.py``'s
    ``session`` fixture deliberately sets ``expire_on_commit=False`` to avoid
    exactly this class of bug, so a pipeline test built on it (``test_pipeline.py``)
    would keep passing even with the bug present -- this is why it shipped
    unnoticed. Routing the question through a stubbed classifier keeps the
    test offline; it is the persistence stage below that this test exists to
    exercise, not retrieval or generation.
    """

    async def fake_classify(_question, *, project_id):
        del project_id
        return RouterOutput(route=QueryRoute.CHARACTER_LOOKUP, subject_phrase="Nobody")

    monkeypatch.setattr(router, "classify_question", fake_classify)

    body = QueryRequest(project_id=project.id, question="Who is Nobody?")

    response = await client.post("/api/query", json=body.model_dump(mode="json"))

    assert response.status_code == 200
    frames = [
        json.loads(line[len("data: ") :])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    event_types = [frame["type"] for frame in frames]

    assert "error" not in event_types, frames
    assert "done" in event_types

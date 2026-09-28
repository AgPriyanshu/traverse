import uuid

import pytest

from api.contracts.api import ChunkOut, SearchResultOut
from api.query import retrieval
from api.query.scope import ReadingScope


def _result(n: int) -> SearchResultOut:
    chunks = [
        ChunkOut(
            id=uuid.uuid4(),
            book_id=uuid.uuid4(),
            text=f"chunk {i}",
            pages=[1],
            page_start=1,
            page_end=1,
        )
        for i in range(n)
    ]
    return SearchResultOut(chunks=chunks)


@pytest.mark.asyncio
async def test_uses_graph_constrained_tier_when_it_finds_something(
    session, monkeypatch
):
    async def fake_hybrid_search(*_args, character_ids=None, **_kwargs):
        return _result(1) if character_ids else _result(0)

    monkeypatch.setattr(retrieval, "hybrid_search", fake_hybrid_search)

    result = await retrieval.retrieve_for_narrative(
        session,
        project_id=uuid.uuid4(),
        question="How does Elizabeth feel about Darcy?",
        character_ids=[uuid.uuid4()],
        scope=ReadingScope.unlimited(),
    )

    assert result.tier == "graph_constrained"
    assert len(result.chunks) == 1


@pytest.mark.asyncio
async def test_falls_back_to_unconstrained_when_constrained_is_empty(
    session, monkeypatch
):
    async def fake_hybrid_search(*_args, character_ids=None, **_kwargs):
        return _result(0) if character_ids else _result(3)

    monkeypatch.setattr(retrieval, "hybrid_search", fake_hybrid_search)

    result = await retrieval.retrieve_for_narrative(
        session,
        project_id=uuid.uuid4(),
        question="How does Elizabeth feel about Darcy?",
        character_ids=[uuid.uuid4()],
        scope=ReadingScope.unlimited(),
    )

    assert result.tier == "unconstrained"
    assert len(result.chunks) == 3


@pytest.mark.asyncio
async def test_skips_straight_to_unconstrained_with_no_resolved_characters(
    session, monkeypatch
):
    calls = []

    async def fake_hybrid_search(*_args, character_ids=None, **_kwargs):
        calls.append(character_ids)
        return _result(2)

    monkeypatch.setattr(retrieval, "hybrid_search", fake_hybrid_search)

    result = await retrieval.retrieve_for_narrative(
        session,
        project_id=uuid.uuid4(),
        question="What is the weather like?",
        character_ids=[],
        scope=ReadingScope.unlimited(),
    )

    assert calls == [None]
    assert result.tier == "unconstrained"


@pytest.mark.asyncio
async def test_tier_is_none_when_nothing_is_found_at_all(session, monkeypatch):
    async def fake_hybrid_search(*_args, **_kwargs):
        return _result(0)

    monkeypatch.setattr(retrieval, "hybrid_search", fake_hybrid_search)

    result = await retrieval.retrieve_for_narrative(
        session,
        project_id=uuid.uuid4(),
        question="Anything?",
        character_ids=[],
        scope=ReadingScope.unlimited(),
    )

    assert result.tier == "none"
    assert result.chunks == []

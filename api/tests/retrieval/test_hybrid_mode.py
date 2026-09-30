import uuid

import pytest

from api.query.scope import ReadingScope
from api.retrieval import RetrievalMode, hybrid_search, repository
from api.retrieval import rerank as rerank_module


@pytest.fixture(autouse=True)
def _stub_embedding(monkeypatch):
    monkeypatch.setattr(repository, "embed_query", lambda text: [0.0])


@pytest.fixture
def calls(monkeypatch):
    seen = {"dense": 0, "lexical": 0, "rerank": 0}

    async def fake_dense(*_args, **_kwargs):
        seen["dense"] += 1
        return []

    async def fake_lexical(*_args, **_kwargs):
        seen["lexical"] += 1
        return []

    def fake_rerank(_query, fused):
        seen["rerank"] += 1
        return fused

    monkeypatch.setattr(repository, "dense_search", fake_dense)
    monkeypatch.setattr(repository, "lexical_search", fake_lexical)
    monkeypatch.setattr(rerank_module, "rerank", fake_rerank)
    monkeypatch.setattr(rerank_module, "reranker_enabled", lambda: False)

    return seen


@pytest.mark.asyncio
async def test_vector_only_never_calls_the_lexical_arm(calls):
    await hybrid_search(
        session=None,
        project_id=uuid.uuid4(),
        query="q",
        scope=ReadingScope.unlimited(),
        mode=RetrievalMode.VECTOR_ONLY,
    )

    assert calls["dense"] == 1
    assert calls["lexical"] == 0
    assert calls["rerank"] == 0


@pytest.mark.asyncio
async def test_bm25_runs_both_arms_but_never_reranks(calls):
    await hybrid_search(
        session=None,
        project_id=uuid.uuid4(),
        query="q",
        scope=ReadingScope.unlimited(),
        mode=RetrievalMode.BM25,
    )

    assert calls["dense"] == 1
    assert calls["lexical"] == 1
    assert calls["rerank"] == 0


@pytest.mark.asyncio
async def test_rerank_mode_forces_rerank_on_regardless_of_the_setting(calls):
    await hybrid_search(
        session=None,
        project_id=uuid.uuid4(),
        query="q",
        scope=ReadingScope.unlimited(),
        mode=RetrievalMode.RERANK,
        character_ids=[uuid.uuid4()],
    )

    assert calls["dense"] == 1
    assert calls["lexical"] == 1
    # RERANK mode drops the graph constraint on purpose -- it is measuring
    # rerank in isolation, one step before graph-constrained in the
    # progression (PRD Appendix A).
    assert calls["rerank"] == 0  # nothing to rerank: both fake arms return []


@pytest.mark.asyncio
async def test_rerank_mode_ignores_character_ids_but_graph_constrained_keeps_them(
    calls, monkeypatch
):
    seen_character_ids: list[object] = []

    async def fake_dense(*_args, character_ids=None, **_kwargs):
        seen_character_ids.append(character_ids)
        return []

    monkeypatch.setattr(repository, "dense_search", fake_dense)

    character_ids = [uuid.uuid4()]
    await hybrid_search(
        session=None,
        project_id=uuid.uuid4(),
        query="q",
        scope=ReadingScope.unlimited(),
        mode=RetrievalMode.RERANK,
        character_ids=character_ids,
    )
    await hybrid_search(
        session=None,
        project_id=uuid.uuid4(),
        query="q",
        scope=ReadingScope.unlimited(),
        mode=RetrievalMode.GRAPH_CONSTRAINED,
        character_ids=character_ids,
    )

    assert seen_character_ids == [None, character_ids]


@pytest.mark.asyncio
async def test_default_mode_is_unchanged_from_pre_s82_behaviour(calls):
    """``mode=None`` (every existing caller) must still run exactly as before."""
    result = await hybrid_search(
        session=None,
        project_id=uuid.uuid4(),
        query="q",
        scope=ReadingScope.unlimited(),
    )

    assert calls["dense"] == 1
    assert calls["lexical"] == 1
    assert result.tier == "unconstrained"

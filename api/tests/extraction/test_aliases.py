import uuid

import pytest

from api.contracts.enums import CandidateKind, ResolutionMethod
from api.extraction import aliases
from api.extraction.schemas import AdjudicationOutput


def _candidate(
    surface_form: str,
    contexts: list[dict],
    *,
    kind: CandidateKind = CandidateKind.PERSON,
) -> object:
    class _Candidate:
        def __init__(self) -> None:
            self.id = uuid.uuid4()
            self.surface_form = surface_form
            self.kind = kind
            self.mention_count = sum(c.get("count", 1) for c in contexts)
            self.contexts = contexts

    return _Candidate()


def _ctx(page: int, text: str, chunk_id: str | None = None) -> dict:
    return {
        "page": page,
        "context": text,
        "chunk_id": chunk_id or str(uuid.uuid4()),
        "chapter_number": None,
        "count": 1,
    }


class TestNormalisedStage:
    async def test_merges_case_and_punctuation_variants(self) -> None:
        candidates = [
            _candidate("Elizabeth", [_ctx(1, "Elizabeth walked in.")]),
            _candidate("elizabeth.", [_ctx(2, "elizabeth. smiled.")]),
        ]

        clusters = await aliases.cluster_candidates(candidates, book_id=uuid.uuid4())

        assert len(clusters) == 1
        assert set(clusters[0].surface_forms) == {"Elizabeth", "elizabeth."}


class TestHonorificStage:
    async def test_merges_a_titled_form_with_the_bare_name(self) -> None:
        candidates = [
            _candidate("Darcy", [_ctx(1, "Darcy frowned.")]),
            _candidate("Mr. Darcy", [_ctx(2, "Mr. Darcy bowed.")]),
        ]

        clusters = await aliases.cluster_candidates(candidates, book_id=uuid.uuid4())

        assert len(clusters) == 1
        assert clusters[0].canonical_name == "Mr. Darcy"
        assert clusters[0].surface_forms["Darcy"] == ResolutionMethod.EXACT
        assert clusters[0].surface_forms["Mr. Darcy"] == ResolutionMethod.HONORIFIC


class TestNicknameStage:
    async def test_merges_a_diminutive_with_the_full_name(self) -> None:
        candidates = [
            _candidate("Elizabeth Bennet", [_ctx(1, "Elizabeth Bennet spoke.")]),
            _candidate("Lizzy Bennet", [_ctx(2, "Lizzy Bennet laughed.")]),
        ]

        clusters = await aliases.cluster_candidates(candidates, book_id=uuid.uuid4())

        assert len(clusters) == 1
        assert clusters[0].canonical_name == "Elizabeth Bennet"
        assert clusters[0].surface_forms["Lizzy Bennet"] == ResolutionMethod.NICKNAME


class TestLLMStage:
    async def test_merges_a_shared_surname_residue_pair(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        candidates = [
            _candidate("Elizabeth Bennet", [_ctx(1, "Elizabeth Bennet spoke first.")]),
            _candidate("Miss Bennet", [_ctx(2, "Miss Bennet smiled.")]),
        ]

        async def fake_adjudicate(*a, **k):
            return AdjudicationOutput(
                same_person=True, confidence=0.9, reason="same speaker"
            )

        monkeypatch.setattr(aliases, "structured_call", fake_adjudicate)

        clusters = await aliases.cluster_candidates(candidates, book_id=uuid.uuid4())

        assert len(clusters) == 1
        assert clusters[0].surface_forms["Miss Bennet"] == ResolutionMethod.LLM

    async def test_collision_blocks_the_merge_before_calling_the_llm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        candidates = [
            _candidate(
                "Catherine Earnshaw",
                [_ctx(10, "Catherine Earnshaw ran across the moor.")],
            ),
            _candidate(
                "Catherine Linton", [_ctx(200, "Catherine Linton sat reading.")]
            ),
        ]

        async def fail(*a, **k):
            raise AssertionError("collision must block before an LLM call")

        monkeypatch.setattr(aliases, "structured_call", fail)

        clusters = await aliases.cluster_candidates(candidates, book_id=uuid.uuid4())

        assert len(clusters) == 2
        assert all(c.collision_suspected for c in clusters)


class TestNoFalsePositiveMerge:
    async def test_unrelated_names_stay_separate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        candidates = [
            _candidate("Elizabeth Bennet", [_ctx(1, "Elizabeth Bennet spoke.")]),
            _candidate("Mr. Wickham", [_ctx(2, "Mr. Wickham arrived.")]),
        ]

        async def fail(*a, **k):
            raise AssertionError("unrelated names should never reach adjudication")

        monkeypatch.setattr(aliases, "structured_call", fail)

        clusters = await aliases.cluster_candidates(candidates, book_id=uuid.uuid4())

        assert len(clusters) == 2

import uuid

import pytest

from api.contracts.enums import CandidateKind
from api.extraction import rejection
from api.extraction.schemas import RejectionOutput


def _candidate(surface_form: str, kind: CandidateKind, contexts: list[dict]) -> object:
    class _Candidate:
        def __init__(self) -> None:
            self.id = uuid.uuid4()
            self.surface_form = surface_form
            self.kind = kind
            self.contexts = contexts

    return _Candidate()


class TestClassifyCandidates:
    async def test_trusts_a_person_guess_without_a_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        candidate = _candidate(
            "Elizabeth", CandidateKind.PERSON, [{"page": 1, "context": "c"}]
        )

        async def fail(*a, **k):
            raise AssertionError("must not call the classifier for a trusted person")

        monkeypatch.setattr(rejection, "structured_call", fail)

        rejections, corrected = await rejection.classify_candidates(
            [candidate], book_id=uuid.uuid4()
        )

        assert rejections == []
        assert corrected == []

    async def test_rejects_a_place(self, monkeypatch: pytest.MonkeyPatch) -> None:
        candidate = _candidate(
            "Longbourn",
            CandidateKind.UNKNOWN,
            [{"page": 3, "context": "They walked to Longbourn."}],
        )

        async def fake(*a, **k):
            return RejectionOutput(
                kind=CandidateKind.PLACE, reason="an estate, not a person"
            )

        monkeypatch.setattr(rejection, "structured_call", fake)

        rejections, corrected = await rejection.classify_candidates(
            [candidate], book_id=uuid.uuid4()
        )

        assert corrected == []
        assert len(rejections) == 1
        assert rejections[0]["candidate_id"] == candidate.id
        assert rejections[0]["kind"] == CandidateKind.PLACE
        assert rejections[0]["reason"] == "an estate, not a person"

    async def test_confirms_an_ambiguous_house_and_family_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        candidate = _candidate(
            "Longbourn",
            CandidateKind.UNKNOWN,
            [{"page": 3, "context": "The Bennets of Longbourn were poor."}],
        )

        async def fake(*a, **k):
            return RejectionOutput(
                kind=CandidateKind.PERSON,
                reason="also names the family",
                is_ambiguous=True,
            )

        monkeypatch.setattr(rejection, "structured_call", fake)

        rejections, corrected = await rejection.classify_candidates(
            [candidate], book_id=uuid.uuid4()
        )

        assert rejections == []
        assert corrected == [candidate.id]

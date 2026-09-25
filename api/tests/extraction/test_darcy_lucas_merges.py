import json
import uuid
from pathlib import Path

import pytest

from api.contracts.enums import CandidateKind
from api.db.models import BookCharacterCandidate
from api.extraction import aliases, similarity
from api.extraction.schemas import AdjudicationOutput

# Every candidate from the real Pride and Prejudice run that touches the Darcy
# or Lucas families (SCR-18/be2's pass-2 recall bug). The model stubs answer
# "same person" to everything, so only the code's own rules keep these apart
# or joined.
FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "pride_and_prejudice_darcy_lucas_candidates.json"
)


@pytest.fixture
async def resolved(monkeypatch: pytest.MonkeyPatch):
    async def always_similar(*a, **k):
        return True

    async def always_same(*a, **k):
        return AdjudicationOutput(same_person=True, confidence=0.95, reason="x")

    monkeypatch.setattr(similarity, "context_similarity", always_similar)
    monkeypatch.setattr(aliases, "structured_call", always_same)

    candidates = [
        BookCharacterCandidate(
            id=uuid.uuid4(),
            book_id=uuid.uuid4(),
            surface_form=row["surface_form"],
            kind=CandidateKind.PERSON,
            mention_count=row["mention_count"],
            contexts=row["contexts"],
        )
        for row in json.loads(FIXTURE.read_text())
    ]

    return await aliases.cluster_candidates(candidates, book_id=uuid.uuid4())


def _cluster_of(resolved, form: str) -> str:
    return next(c.canonical_name for c in resolved if form in c.surface_forms)


def test_fitzwilliam_darcy_forms_merge_into_mr_darcy(resolved) -> None:
    target = _cluster_of(resolved, "Mr. Darcy")

    assert _cluster_of(resolved, "Mr. Fitzwilliam Darcy") == target
    assert _cluster_of(resolved, "FITZWILLIAM DARCY") == target
    assert _cluster_of(resolved, "Fitzwilliam") == target
    assert _cluster_of(resolved, "Darcy") == target


def test_miss_darcy_stays_separate_from_mr_darcy(resolved) -> None:
    assert _cluster_of(resolved, "Miss Darcy") != _cluster_of(resolved, "Mr. Darcy")


def test_lady_lucas_is_not_merged_into_her_daughter(resolved) -> None:
    charlotte = _cluster_of(resolved, "Charlotte Lucas")

    assert _cluster_of(resolved, "Lady Lucas") != charlotte
    assert "Lady Lucas" not in next(
        c.surface_forms for c in resolved if c.canonical_name == charlotte
    )


def test_maiden_and_married_names_stay_apart_without_a_textual_cue(resolved) -> None:
    # Charlotte's marriage is never announced in her own mention contexts
    # ("Mrs. Collins, formerly Charlotte Lucas" or similar never appears) --
    # merging on convention alone would be a guess, so this pins the current,
    # honest behaviour rather than asserting the (unreachable) ideal one.
    assert _cluster_of(resolved, "Charlotte Lucas") != _cluster_of(
        resolved, "Mrs. Collins"
    )

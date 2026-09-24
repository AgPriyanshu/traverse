import json
import uuid
from pathlib import Path

import pytest

from api.contracts.enums import CandidateKind
from api.db.models import BookCharacterCandidate
from api.extraction import aliases, similarity
from api.extraction.schemas import AdjudicationOutput

# Candidates and contexts exported from the real Pride and Prejudice run. The
# stubs below say "same person" to everything: a model asked about two similar
# contexts does say that, and the rules under test must hold anyway.
FIXTURE = (
    Path(__file__).parent / "fixtures" / "pride_and_prejudice_family_candidates.json"
)


@pytest.fixture
async def clusters(monkeypatch: pytest.MonkeyPatch) -> dict[str, set[str]]:
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
    resolved = await aliases.cluster_candidates(candidates, book_id=uuid.uuid4())

    return {c.canonical_name: set(c.surface_forms) for c in resolved}


def _cluster_of(clusters: dict[str, set[str]], form: str) -> str:
    return next(name for name, forms in clusters.items() if form in forms)


def test_mr_bingley_is_not_caroline_bingley(clusters) -> None:
    assert _cluster_of(clusters, "Mr. Bingley") != _cluster_of(clusters, "Miss Bingley")
    assert _cluster_of(clusters, "Miss Bingley") == _cluster_of(
        clusters, "Caroline Bingley"
    )
    assert _cluster_of(clusters, "Bingley") == _cluster_of(clusters, "Mr. Bingley")


def test_bare_darcy_joins_mr_darcy_not_miss_darcy(clusters) -> None:
    assert _cluster_of(clusters, "Darcy") == _cluster_of(clusters, "Mr. Darcy")
    assert _cluster_of(clusters, "Miss Darcy") != _cluster_of(clusters, "Mr. Darcy")


def test_miss_bennet_does_not_fold_into_one_of_several_sisters(clusters) -> None:
    miss_bennet = _cluster_of(clusters, "Miss Bennet")

    assert miss_bennet != _cluster_of(clusters, "Lydia")
    assert miss_bennet != _cluster_of(clusters, "Elizabeth")


def test_lady_lucas_is_not_her_daughter(clusters) -> None:
    assert _cluster_of(clusters, "Lady Lucas") != _cluster_of(clusters, "Charlotte")
    assert _cluster_of(clusters, "Lady Lucas") != _cluster_of(clusters, "Maria Lucas")


def test_mr_and_mrs_bennet_and_elizabeth_stay_three_people(clusters) -> None:
    names = {
        _cluster_of(clusters, form)
        for form in ("Mr. Bennet", "Mrs. Bennet", "Elizabeth")
    }

    assert len(names) == 3


def test_elizabeth_still_collects_her_forms(clusters) -> None:
    assert (
        _cluster_of(clusters, "Lizzy")
        == _cluster_of(clusters, "Elizabeth")
        == _cluster_of(clusters, "Miss Elizabeth Bennet")
    )

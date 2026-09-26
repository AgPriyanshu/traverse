import json
import uuid
from pathlib import Path

import pytest

from api.contracts.enums import CandidateKind
from api.db.models import BookCharacterCandidate
from api.extraction import aliases, similarity
from api.extraction.schemas import AdjudicationOutput

# Every "Bennet"-family candidate from the real Pride and Prejudice run
# (be2/fe1's roster5 finding: "Jane" and "Miss Bennet" look like the same
# person split across two rows). The model stub answers "same person" to
# everything, so only the code's own rules keep these apart or joined.
FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "pride_and_prejudice_jane_bennet_candidates.json"
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


def test_jane_and_miss_bennet_stay_separate_without_a_shared_token(resolved) -> None:
    # "Jane" and "Miss Bennet" share no first/last token once "Miss" is
    # stripped ("Jane" vs "Bennet"), so the cascade's blocking-pairs step
    # never proposes them as a pair -- not a wrong merge decision, no merge
    # decision is ever made. This pins that current, honest behaviour: see
    # the next test for why merging them by convention alone would be
    # actively wrong here, not merely unproven.
    assert _cluster_of(resolved, "Jane") != _cluster_of(resolved, "Miss Bennet")


def test_miss_bennet_is_not_safely_mergeable_by_the_eldest_daughter_convention(
    resolved,
) -> None:
    # Most of "Miss Bennet"'s 23 mentions are the Regency convention that the
    # bare "Miss <Surname>" names the eldest unmarried daughter -- Jane, here.
    # But one of this candidate's own stored contexts is Lady Catherine's
    # chapter-56 confrontation ("You can be at no loss, Miss Bennet, to
    # understand the reason of my journey hither"), which the source text
    # (corpus/downloads/pride-and-prejudice.txt, "Elizabeth obeyed; and,
    # running into her own room for her parasol...") confirms is addressed to
    # Elizabeth, not Jane. A blanket merge into "Jane" would misattribute
    # that scene -- and any pass-2 relation evidence drawn from it -- to the
    # wrong character. This is a real within-book collision on the surface
    # form, the same class of risk collision.py's sibling-ambiguity veto
    # exists to catch, just not one reachable through a shared token here.
    miss_bennet = next(
        c for c in resolved if "Miss Bennet" in c.surface_forms
    )
    contexts = [ctx["context"] for ctx in miss_bennet.contexts]

    assert any("at no loss, Miss Bennet" in ctx for ctx in contexts)
    assert _cluster_of(resolved, "Miss Bennet") != _cluster_of(
        resolved, "Elizabeth Bennet"
    )

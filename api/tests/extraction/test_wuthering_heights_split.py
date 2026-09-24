import json
import uuid
from pathlib import Path

import pytest

from api.contracts.enums import CandidateKind
from api.db.models import BookCharacterCandidate
from api.extraction import aliases, similarity
from api.extraction.schemas import AdjudicationOutput

# Every candidate from the real Wuthering Heights run. The model stubs answer
# "same person" to everything, so only the code's own rules can keep the two
# Catherines apart.
FIXTURE = Path(__file__).parent / "fixtures" / "wuthering_heights_candidates.json"
BIRTH_PAGE = 102


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


def _cluster(resolved, canonical: str):
    return next(c for c in resolved if c.canonical_name == canonical)


def _bare_pages(cluster) -> list[int]:
    bare = {"Catherine", "Cathy", "Miss Cathy", "Miss Catherine"}

    return [c["page"] for c in cluster.contexts if c["surface_form"] in bare]


def test_the_two_catherines_are_two_characters(resolved) -> None:
    names = {c.canonical_name for c in resolved}

    assert {"Catherine Earnshaw", "Catherine Linton"} <= names


def test_bare_catherine_before_the_daughters_birth_is_the_elder(resolved) -> None:
    elder_pages = _bare_pages(_cluster(resolved, "Catherine Earnshaw"))

    assert elder_pages
    assert max(elder_pages) < BIRTH_PAGE


def test_bare_catherine_after_the_birth_is_the_younger(resolved) -> None:
    younger_pages = _bare_pages(_cluster(resolved, "Catherine Linton"))

    assert younger_pages
    assert min(younger_pages) >= BIRTH_PAGE


def test_the_elder_holds_a_real_share_of_the_mentions(resolved) -> None:
    elder = _cluster(resolved, "Catherine Earnshaw")
    younger = _cluster(resolved, "Catherine Linton")

    assert elder.total_mentions > 30
    assert younger.total_mentions > 30


def test_no_bare_form_is_lost_in_the_split(resolved) -> None:
    total = sum(
        c.mention_counts.get(form, 0)
        for c in resolved
        if c.canonical_name in {"Catherine Earnshaw", "Catherine Linton"}
        for form in ("Catherine", "Cathy", "Miss Cathy", "Miss Catherine")
    )

    assert total == 145 + 28 + 11 + 4


def test_nelly_ellen_and_mrs_dean_are_one_person(resolved) -> None:
    dean = _cluster(resolved, "Ellen Dean")

    assert {"Nelly", "Ellen", "Mrs. Dean", "Nelly Dean"} <= set(dean.surface_forms)


def test_edgar_forms_gather_and_the_boy_master_linton_stays_apart(resolved) -> None:
    edgar = _cluster(resolved, "Edgar Linton")

    assert {"Edgar", "Mr. Edgar", "Mr. Linton"} <= set(edgar.surface_forms)
    assert "Master Linton" not in edgar.surface_forms


def test_old_mr_earnshaw_is_neither_hindley_nor_hareton(resolved) -> None:
    father = next(c for c in resolved if "Mr. Earnshaw" in c.surface_forms)

    assert father.canonical_name == "Mr. Earnshaw"
    assert "Hindley" not in father.surface_forms
    assert "Hareton" not in father.surface_forms


def test_isabella_is_not_split_by_an_unrelated_young_linton(resolved) -> None:
    isabella = _cluster(resolved, "Isabella Linton")

    assert "Isabella" in isabella.surface_forms

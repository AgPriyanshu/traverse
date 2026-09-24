import uuid

import pytest

from api.contracts.enums import CandidateKind
from api.extraction import aliases, rejection, similarity
from api.extraction.filtering import plausible_character_name
from api.extraction.schemas import AdjudicationOutput, RejectionOutput


@pytest.mark.parametrize(
    "form",
    ["she", "He", "I", "you", "Mr.", "Mrs.", "the housekeeper", "my brother Gardiner"]
    + ["Mr. and Mrs. Gardiner", "her sister", "_We_", "madam", "people", "a woman"],
)
def test_rejects_what_can_never_be_a_name(form: str) -> None:
    assert not plausible_character_name(form)


@pytest.mark.parametrize(
    "form",
    ["Mr. Darcy", "Elizabeth", "Lady Catherine de Bourgh", "M. de Maupassant"]
    + ["GARDINER.", "Sir William Lucas's", "Miss de Bourgh", "Kitty"],
)
def test_keeps_proper_names(form: str) -> None:
    assert plausible_character_name(form)


def _candidate(form: str, count: int, chapter: int | None = 3) -> object:
    class _Candidate:
        def __init__(self) -> None:
            self.id = uuid.uuid4()
            self.surface_form = form
            self.kind = CandidateKind.PERSON
            self.mention_count = count
            self.contexts = [
                {
                    "page": 5,
                    "context": f"{form} spoke at length in the room.",
                    "chunk_id": str(uuid.uuid4()),
                    "chapter_number": chapter,
                    "count": count,
                }
            ]

    return _Candidate()


async def _cluster(forms: list[tuple[str, int]], monkeypatch: pytest.MonkeyPatch):
    async def never_same(*a, **k):
        return AdjudicationOutput(same_person=False, confidence=0.9, reason="no")

    async def never_similar(*a, **k):
        return False

    monkeypatch.setattr(aliases, "structured_call", never_same)
    monkeypatch.setattr(similarity, "context_similarity", never_similar)
    candidates = [_candidate(form, count) for form, count in forms]

    return await aliases.cluster_candidates(candidates, book_id=uuid.uuid4())


async def test_pronouns_never_become_characters(monkeypatch) -> None:
    clusters = await _cluster([("Elizabeth", 50), ("she", 40), ("he", 41)], monkeypatch)

    assert [c.canonical_name for c in clusters] == ["Elizabeth"]


async def test_given_name_folds_into_the_one_full_name(monkeypatch) -> None:
    clusters = await _cluster(
        [("Elizabeth", 180), ("Elizabeth Bennet", 4), ("Lizzy", 5)], monkeypatch
    )

    assert len(clusters) == 1
    assert clusters[0].canonical_name == "Elizabeth Bennet"


async def test_mr_and_miss_of_one_surname_stay_apart(monkeypatch) -> None:
    clusters = await _cluster(
        [("Mr. Darcy", 344), ("Darcy", 27), ("Miss Darcy", 23)], monkeypatch
    )

    forms = {c.canonical_name: set(c.surface_forms) for c in clusters}
    assert forms == {"Mr. Darcy": {"Mr. Darcy", "Darcy"}, "Miss Darcy": {"Miss Darcy"}}


async def test_titled_surname_does_not_fold_into_another_given_name(
    monkeypatch,
) -> None:
    clusters = await _cluster(
        [("Mr. Bennet", 89), ("Elizabeth Bennet", 7), ("Bennet", 3)], monkeypatch
    )

    assert len(clusters) == 2


async def test_possessive_and_case_variants_merge(monkeypatch) -> None:
    clusters = await _cluster(
        [("Wickham", 23), ("Wickham's", 1), ("GARDINER.", 1), ("Gardiner", 4)],
        monkeypatch,
    )

    assert len(clusters) == 2


async def test_front_matter_candidates_are_rejected(monkeypatch) -> None:
    async def person(*a, **k):
        return RejectionOutput(
            kind=CandidateKind.PERSON, reason="x", is_ambiguous=False
        )

    monkeypatch.setattr(rejection, "structured_call", person)
    candidates = [
        _candidate("Elizabeth", 180, chapter=2),
        _candidate("Thackeray", 2, chapter=None),
    ]

    rejections, _ = await rejection.classify_candidates(
        candidates, book_id=uuid.uuid4()
    )

    assert [r["candidate_id"] for r in rejections] == [candidates[1].id]


async def test_no_front_matter_rejection_when_no_chapters_were_detected(
    monkeypatch,
) -> None:
    async def person(*a, **k):
        return RejectionOutput(
            kind=CandidateKind.PERSON, reason="x", is_ambiguous=False
        )

    monkeypatch.setattr(rejection, "structured_call", person)
    candidates = [_candidate("Elizabeth", 180, chapter=None)]

    rejections, _ = await rejection.classify_candidates(
        candidates, book_id=uuid.uuid4()
    )

    assert rejections == []

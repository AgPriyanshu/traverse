"""The sprint's headline regression test (backend-1.md S3.4).

``test_wuthering_heights_two_catherines`` is named exactly as the plan
requires and must stay in the permanent regression suite. ``test_no_false_splits``
is its counterweight: the same cascade must not fragment a character (Elizabeth
Bennet) whose aliases merely look superficially different.
"""

import uuid

import pytest

from api.extraction import aliases
from api.extraction.schemas import AdjudicationOutput


def _candidate(surface_form: str, contexts: list[dict]) -> object:
    from api.contracts.enums import CandidateKind

    class _Candidate:
        def __init__(self) -> None:
            self.id = uuid.uuid4()
            self.surface_form = surface_form
            self.kind = CandidateKind.PERSON
            self.mention_count = sum(c.get("count", 1) for c in contexts)
            self.contexts = contexts

    return _Candidate()


def _ctx(page: int, text: str) -> dict:
    return {
        "page": page,
        "context": text,
        "chunk_id": str(uuid.uuid4()),
        "chapter_number": None,
        "count": 1,
    }


async def test_wuthering_heights_two_catherines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catherine Earnshaw and Catherine Linton must resolve to two characters.

    Even if an LLM adjudicator would say "same person" from string
    similarity alone, the collision guard must block the merge outright on
    the generational marker and the mother's death preceding the
    daughter's introduction — this test asserts that even a maximally
    permissive adjudicator cannot force the merge.
    """
    candidates = [
        _candidate(
            "Catherine Earnshaw",
            [
                _ctx(12, "Catherine Earnshaw grew wild on the moors."),
                _ctx(140, "Catherine Earnshaw died, worn out by grief."),
            ],
        ),
        _candidate(
            "Catherine Linton",
            [
                _ctx(210, "young Catherine Linton was born at the Grange."),
                _ctx(260, "Catherine Linton, her mother's name was Catherine too."),
            ],
        ),
    ]

    async def always_same_person(*a, **k):
        return AdjudicationOutput(
            same_person=True, confidence=0.99, reason="looks related"
        )

    monkeypatch.setattr(aliases, "structured_call", always_same_person)

    clusters = await aliases.cluster_candidates(candidates, book_id=uuid.uuid4())

    names = {c.canonical_name for c in clusters}
    assert names == {"Catherine Earnshaw", "Catherine Linton"}
    assert all(c.collision_suspected for c in clusters)


async def test_no_false_splits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Elizabeth Bennet's aliases must converge on one character, not fragment."""
    candidates = [
        _candidate("Elizabeth Bennet", [_ctx(1, "Elizabeth Bennet arrived first.")]),
        _candidate("Elizabeth", [_ctx(3, "Elizabeth laughed at the remark.")]),
        _candidate("Lizzy", [_ctx(5, "Lizzy teased her sister.")]),
        _candidate("Eliza", [_ctx(9, "Eliza played the pianoforte.")]),
        _candidate(
            "Miss Elizabeth Bennet", [_ctx(20, "Miss Elizabeth Bennet declined.")]
        ),
        _candidate("Miss Bennet", [_ctx(40, "Miss Bennet was, by general consent,")]),
    ]

    async def always_same_person(*a, **k):
        return AdjudicationOutput(
            same_person=True, confidence=0.95, reason="context matches Elizabeth"
        )

    monkeypatch.setattr(aliases, "structured_call", always_same_person)

    clusters = await aliases.cluster_candidates(candidates, book_id=uuid.uuid4())

    assert len(clusters) == 1
    assert clusters[0].canonical_name in {"Elizabeth Bennet", "Miss Elizabeth Bennet"}
    assert not clusters[0].collision_suspected

import uuid

import pytest

from api.contracts.enums import AssertionType, ImportanceTier
from api.graph import ontology
from api.relations import extract, prompts
from api.relations.aggregate import Fact, aggregate, edge_confidence
from api.relations.canonical import canonical_direction, is_canonical_predicate
from api.relations.roster import Roster, RosterEntry
from api.relations.schemas import RawRelation, RelationSweepOutput
from api.relations.validator import RejectionStats, quote_in_chunk, validate

A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
BOOK = uuid.uuid4()
TEXT = "Mr. Darcy proposed to Elizabeth Bennet. Charles Bingley smiled."


def roster(order: list[int] | None = None) -> Roster:
    entries = [
        RosterEntry(
            A, "Fitzwilliam Darcy", ("Mr. Darcy", "Darcy"), ImportanceTier.MAJOR
        ),
        RosterEntry(B, "Elizabeth Bennet", ("Lizzy",), ImportanceTier.PROTAGONIST),
        RosterEntry(C, "Charles Bingley", ("Mr. Bingley",), ImportanceTier.MAJOR),
    ]
    if order:
        entries = [entries[i] for i in order]

    return Roster(entries)


def raw(**kw) -> RawRelation:
    base = {
        "subject": "Mr. Darcy",
        "predicate": "engaged_to",
        "object": "Elizabeth Bennet",
        "quote": "Mr. Darcy proposed to Elizabeth Bennet.",
    }

    return RawRelation(**{**base, **kw})


def fact(s, p, o, chapter, quote, kind=AssertionType.NARRATED, by=None) -> Fact:
    return Fact(
        s, p, o, uuid.uuid4(), BOOK, 1, chapter, chapter, chapter, quote, kind, by, 0.9
    )


def test_prefix_is_byte_identical_regardless_of_roster_input_order():
    one = prompts.build_prefix(roster([0, 1, 2]).prompt_block())
    two = prompts.build_prefix(roster([2, 0, 1]).prompt_block())

    assert one == two


def test_alias_resolves_to_canonical_and_ambiguity_resolves_to_nobody():
    r = roster()

    assert r.resolve("Mr. Bingley") == C
    assert r.resolve("darcy") == A
    assert r.resolve("Nobody Atall") is None


def test_validator_counts_reasons_and_catches_fabricated_quote():
    stats = RejectionStats()
    r = roster()
    good = validate(raw(), TEXT, r, stats)
    validate(raw(subject="Jane Fairfax"), TEXT, r, stats)
    validate(raw(object="Mr. Darcy"), TEXT, r, stats)
    validate(raw(quote="Darcy adored her from the first day."), TEXT, r, stats)
    validate(raw(quote="Charles Bingley smiled."), TEXT, r, stats)

    assert good is not None and good.subject_id == A
    assert stats.by_reason["off_roster_subject"] == 1
    assert stats.by_reason["self_relation"] == 1
    assert stats.by_reason["quote_not_in_chunk"] == 1
    assert stats.by_reason["quote_names_other_characters"] == 1


def test_off_ontology_predicate_cannot_be_constructed_or_validated():
    with pytest.raises(ValueError):
        RawRelation(subject="a", predicate="acquainted_with", object="b", quote="q")

    assert not ontology.is_predicate("acquainted_with")
    assert quote_in_chunk("mr.  darcy PROPOSED", TEXT)


def test_canonical_direction_merges_inverse_and_symmetric():
    assert canonical_direction(A, "child_of", B) == canonical_direction(
        B, "parent_of", A
    )
    assert canonical_direction(A, "sibling_of", B) == canonical_direction(
        B, "sibling_of", A
    )
    for name, spec in ontology.PREDICATES.items():
        if spec.inverse and spec.inverse != name:
            assert is_canonical_predicate(name) != is_canonical_predicate(spec.inverse)


def test_forty_assertions_become_one_edge_with_forty_evidence_items():
    facts = [fact(A, "friend_of", B, 1 + i % 5, f"quote {i}") for i in range(40)]
    result = aggregate(facts)

    assert len(result.relations) == 1
    assert len(result.relations[0].evidence) == 40


def test_inverse_and_symmetric_duplicates_collapse():
    facts = [
        fact(A, "child_of", B, 1, "one"),
        fact(B, "parent_of", A, 2, "two"),
        fact(A, "sibling_of", C, 1, "three"),
        fact(C, "sibling_of", A, 2, "four"),
    ]
    result = aggregate(facts)

    assert sorted(len(r.evidence) for r in result.relations) == [2, 2]


def test_transition_closes_the_earlier_edge_and_keeps_it():
    facts = [
        fact(A, "enemy_of", B, 3, "a"),
        fact(A, "engaged_to", B, 40, "b"),
        fact(A, "married_to", B, 60, "c"),
    ]
    by_pred = {r.predicate: r for r in aggregate(facts).relations}

    assert by_pred["enemy_of"].status == "superseded"
    assert by_pred["enemy_of"].last.chapter == 40
    assert by_pred["engaged_to"].last.chapter == 60
    assert by_pred["married_to"].status == "active"


def test_dialogue_only_edge_is_hearsay_with_speaker():
    result = aggregate([fact(A, "friend_of", B, 1, "q", AssertionType.DIALOGUE, C)])
    edge = result.relations[0]

    assert edge.hearsay and edge.asserted_by_character_id == C
    assert not aggregate([fact(A, "friend_of", B, 1, "q")]).relations[0].hearsay


def test_conflict_is_reported_not_resolved():
    facts = [fact(A, "parent_of", B, 1, "a"), fact(B, "parent_of", A, 2, "b")]
    result = aggregate(facts)

    assert len(result.relations) == 2
    assert result.conflicts


def test_confidence_ignores_model_self_report_ceiling():
    assert edge_confidence(1, 1.0, [1.0]) < edge_confidence(5, 1.0, [1.0]) <= 0.99


@pytest.mark.asyncio
async def test_length_limit_splits_the_chunk_and_quotes_check_against_full_chunk(
    monkeypatch,
):
    from api.db.models import DocumentChunk
    from api.llm import LengthLimitError

    body = ("Mr. Darcy proposed to Elizabeth Bennet. " * 30).strip()
    chunk = DocumentChunk(
        id=uuid.uuid4(), book_id=BOOK, text=body, pages=[1], page_start=1, page_end=1
    )
    calls = []

    async def fake(prompt, schema, **kw):
        calls.append(prompt)
        if len(calls) == 1:
            raise LengthLimitError("cut off")
        return RelationSweepOutput(relations=[raw()])

    async def verified(*a, **k):
        return [True, True]

    monkeypatch.setattr(extract, "structured_call", fake)
    monkeypatch.setattr(extract.verify, "verify_many", verified)
    result = await extract.extract_book([(chunk, 1)], roster(), book_id=BOOK)

    assert result.length_splits == 1 and result.calls == 3
    assert len(result.facts) == 2

import json

import pytest

from eval.loaders import (
    REPO_ROOT,
    CorpusChecksumMismatch,
    available_gold_answer_books,
    available_gold_books,
    available_gold_identity_series,
    load_gold_answers,
    load_gold_identity,
    load_gold_roster,
)


def test_both_gold_rosters_are_schema_valid_and_checksum_pinned():
    books = available_gold_books()

    assert "pride-and-prejudice" in books
    assert "wuthering-heights" in books
    for book_key in ("pride-and-prejudice", "wuthering-heights"):
        roster = load_gold_roster(book_key)
        assert roster["book_key"] == book_key
        assert len(roster["characters"]) > 0


def test_gold_answers_are_schema_valid_and_checksum_pinned():
    books = available_gold_answer_books()

    assert "pride-and-prejudice" in books
    document = load_gold_answers("pride-and-prejudice")
    assert document["book_key"] == "pride-and-prejudice"
    questions = document["questions"]
    assert len(questions) == 30
    classes = {q["class"] for q in questions}
    assert classes == {
        "single_fact",
        "relationship",
        "path",
        "aggregation",
        "temporal",
        "unanswerable",
    }
    # F4.1: abstention is a first-class expectation, not an afterthought --
    # every unanswerable question must actually say so.
    for q in questions:
        assert q["expect_abstain"] == (q["class"] == "unanswerable")


def test_wuthering_heights_gold_roster_keeps_the_two_catherines_separate():
    roster = load_gold_roster("wuthering-heights")
    catherines = [
        c for c in roster["characters"] if c["canonical_name"].startswith("Catherine")
    ]

    assert len(catherines) == 2
    names = {c["canonical_name"] for c in catherines}
    assert names == {"Catherine Earnshaw", "Catherine Linton"}
    assert all(c.get("collision_group") == "catherine" for c in catherines)


def test_checksum_mismatch_fails_loudly_not_silently():
    manifest_path = REPO_ROOT / "corpus" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["books"]["pride-and-prejudice"]["pdf_sha256"] = "0" * 64

    original = manifest_path.read_text()
    try:
        manifest_path.write_text(json.dumps(manifest))
        with pytest.raises(CorpusChecksumMismatch, match="repaginated"):
            load_gold_roster("pride-and-prejudice")
    finally:
        manifest_path.write_text(original)


def test_verify_checksum_false_skips_the_pin_check():
    manifest_path = REPO_ROOT / "corpus" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["books"]["pride-and-prejudice"]["pdf_sha256"] = "0" * 64

    original = manifest_path.read_text()
    try:
        manifest_path.write_text(json.dumps(manifest))
        load_gold_roster("pride-and-prejudice", verify_checksum=False)
    finally:
        manifest_path.write_text(original)


def test_gold_rosters_cover_the_named_cast_and_have_unique_canonical_names():
    for key in ("pride-and-prejudice", "wuthering-heights"):
        roster = load_gold_roster(key)
        names = [c["canonical_name"] for c in roster["characters"]]

        assert len(names) == len(set(names)), key
        assert len(names) >= 20, key
        assert any(c["importance_tier"] == "mentioned" for c in roster["characters"])


def test_anne_gold_identity_is_schema_valid_and_checksum_pinned():
    assert "anne-of-green-gables" in available_gold_identity_series()

    document = load_gold_identity("anne-of-green-gables")

    assert document["series_key"] == "anne-of-green-gables"
    assert [b["book_order"] for b in document["books"]] == [1, 2, 3]
    names = [c["canonical"] for c in document["characters"]]
    assert len(names) == len(set(names))
    assert "Anne Shirley" in names


def test_anne_gold_identity_has_a_death_and_a_new_in_book_3_case():
    document = load_gold_identity("anne-of-green-gables")
    by_name = {c["canonical"]: c for c in document["characters"]}

    assert by_name["Matthew Cuthbert"]["dies_in_book"] == 1
    assert by_name["Matthew Cuthbert"]["appears_in"] == [1]
    assert by_name["Priscilla Grant"]["appears_in"] == [3]


def test_identity_checksum_mismatch_fails_loudly():
    manifest_path = REPO_ROOT / "corpus" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["books"]["anne-of-green-gables"]["pdf_sha256"] = "0" * 64

    original = manifest_path.read_text()
    try:
        manifest_path.write_text(json.dumps(manifest))
        with pytest.raises(CorpusChecksumMismatch, match="regenerated"):
            load_gold_identity("anne-of-green-gables")
    finally:
        manifest_path.write_text(original)

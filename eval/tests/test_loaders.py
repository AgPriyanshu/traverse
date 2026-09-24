import json

import pytest

from eval.loaders import (
    REPO_ROOT,
    CorpusChecksumMismatch,
    available_gold_books,
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

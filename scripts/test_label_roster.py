"""Unit tests for the pure parts of scripts/label_roster.py (S3.13).

The review loop takes an injectable `input_fn`/`print_fn` specifically so it
can be scripted here without a real terminal -- see its docstring.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.loaders import load_gold_roster  # noqa: E402
from scripts.label_roster import (  # noqa: E402
    Candidate,
    load_candidates_from_json,
    review_candidates,
    write_roster,
)


def _scripted_input(answers: list[str]):
    it = iter(answers)

    def _input(_prompt: str) -> str:
        return next(it)

    return _input


def test_confirm_keeps_the_candidate_unchanged():
    candidates = [Candidate("Elizabeth Bennet", ["Lizzy"], "protagonist", 13)]

    characters, rejected = review_candidates(
        candidates, input_fn=_scripted_input(["c"]), print_fn=lambda _: None
    )

    assert characters == [
        {
            "canonical_name": "Elizabeth Bennet",
            "aliases": ["Lizzy"],
            "importance_tier": "protagonist",
            "first_page": 13,
        }
    ]
    assert rejected == []


def test_reject_records_a_reason_and_drops_it_from_characters():
    candidates = [Candidate("Netherfield", [], "mentioned", 12)]

    characters, rejected = review_candidates(
        candidates,
        input_fn=_scripted_input(["r", "a place, not a person"]),
        print_fn=lambda _: None,
    )

    assert characters == []
    assert rejected == [
        {"surface_form": "Netherfield", "reason": "a place, not a person"}
    ]


def test_edit_overrides_fields_then_confirms():
    candidates = [Candidate("Kitty", [], "mentioned", 14)]

    characters, _ = review_candidates(
        candidates,
        input_fn=_scripted_input(
            ["e", "Kitty Bennet", "Kitty, Catherine Bennet", "minor", "14"]
        ),
        print_fn=lambda _: None,
    )

    assert characters == [
        {
            "canonical_name": "Kitty Bennet",
            "aliases": ["Kitty", "Catherine Bennet"],
            "importance_tier": "minor",
            "first_page": 14,
        }
    ]


def test_split_produces_two_characters_from_one_candidate():
    # The two-Catherines shape, run forward: the system proposed one merged
    # "Catherine" candidate and the reviewer splits it into two real people.
    candidates = [Candidate("Catherine", ["Cathy"], "protagonist", 12)]

    characters, _ = review_candidates(
        candidates,
        input_fn=_scripted_input(
            [
                "s",
                "Catherine Linton",
                "Catherine, Cathy, young Catherine",
                "major",
                "102",
            ]
        ),
        print_fn=lambda _: None,
    )

    assert len(characters) == 2
    assert characters[0]["canonical_name"] == "Catherine"
    assert characters[1] == {
        "canonical_name": "Catherine Linton",
        "aliases": ["Catherine", "Cathy", "young Catherine"],
        "importance_tier": "major",
        "first_page": 102,
    }


def test_skip_leaves_the_candidate_out_of_both_lists():
    candidates = [Candidate("Duplicate Entry", [], "mentioned", 1)]

    characters, rejected = review_candidates(
        candidates, input_fn=_scripted_input(["skip"]), print_fn=lambda _: None
    )

    assert characters == []
    assert rejected == []


def test_load_candidates_from_json_round_trips(tmp_path: Path):
    path = tmp_path / "candidates.json"
    path.write_text(
        json.dumps(
            [
                {
                    "canonical_name": "Heathcliff",
                    "aliases": [],
                    "importance_tier": "protagonist",
                }
            ]
        )
    )

    candidates = load_candidates_from_json(path)

    assert candidates == [Candidate("Heathcliff", [], "protagonist", None)]


def test_write_roster_pins_the_live_manifest_checksum_and_round_trips():
    # Writes into a throwaway book key, never a real committed gold file --
    # eval/gold/pride_and_prejudice/roster.yaml is hand-commented, and
    # round-tripping it through yaml.safe_load/safe_dump would silently
    # discard every comment in it.
    from eval.loaders import GOLD_DIR, REPO_ROOT

    manifest_path = REPO_ROOT / "corpus" / "manifest.json"
    original_bytes = manifest_path.read_text()
    manifest = json.loads(original_bytes)
    manifest["books"]["test-scratch-book"] = dict(
        manifest["books"]["pride-and-prejudice"]
    )

    characters = [
        {
            "canonical_name": "Test Character",
            "aliases": ["Testy"],
            "importance_tier": "minor",
            "first_page": 1,
        }
    ]
    scratch_dir = GOLD_DIR / "test_scratch_book"

    try:
        manifest_path.write_text(json.dumps(manifest))
        written_path = write_roster(
            "test-scratch-book", characters, [], labelled_by="test"
        )
        assert written_path.exists()

        reloaded = load_gold_roster("test-scratch-book")
        assert reloaded["characters"] == characters
        assert (
            reloaded["corpus_pdf_sha256"]
            == manifest["books"]["pride-and-prejudice"]["pdf_sha256"]
        )
    finally:
        manifest_path.write_text(original_bytes)
        if scratch_dir.exists():
            for child in scratch_dir.iterdir():
                child.unlink()
            scratch_dir.rmdir()

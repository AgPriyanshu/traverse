from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import publish_ablation_readme as gen

SAMPLE_ARTIFACT = {
    "run_id": "2026-09-28T000000Z",
    "generated_at": "2026-09-28T00:00:00+00:00",
    "git_sha": "abc123def456abc123def456abc123def456abc1",
    "corpus_version": "2026-09-22T16:03:26+00:00",
    "summary": {"total_rows": 3, "measured": 1, "blocked": 1, "partial": 1},
    "cells": [
        {
            "axis": "extraction",
            "label": "Two-pass, full alias cascade (recommended)",
            "recommended": True,
            "book_key": "pride-and-prejudice",
            "status": "measured",
            "blocked_reason": None,
            "metrics": {"precision": 0.75, "recall": 0.65, "f1": 0.70, "sample_size": 52},
        },
        {
            "axis": "extraction",
            "label": "Single-pass, string-only aliases",
            "recommended": False,
            "book_key": None,
            "status": "blocked",
            "blocked_reason": "blocked: no ablation config-switch exists yet",
            "metrics": {"sample_size": 0},
        },
        {
            "axis": "retrieval",
            "label": "Graph-constrained + evidence hydration (recommended)",
            "recommended": True,
            "book_key": "pride-and-prejudice",
            "status": "partial",
            "blocked_reason": "blocked: needs a frontier judge (partial run: 19/30 answered)",
            "metrics": {"accuracy": None, "precision": None, "sample_size": 19},
        },
    ],
}


def test_render_section_includes_run_metadata():
    section = gen.render_section(SAMPLE_ARTIFACT)

    assert "2026-09-28T000000Z" in section
    assert "abc123def456" in section
    assert "1 measured, 1 partial, 1 blocked of 3 rows" in section


def test_render_section_includes_every_axis_present():
    section = gen.render_section(SAMPLE_ARTIFACT)

    assert "Extraction" in section
    assert "Retrieval" in section
    assert "Model" not in section  # no model-axis cells in this sample


def test_render_section_shows_real_numbers_for_measured_cells():
    section = gen.render_section(SAMPLE_ARTIFACT)

    assert "0.700" in section  # extraction f1
    assert "pride-and-prejudice" in section


def test_render_section_marks_blocked_cells_and_lists_the_reason():
    section = gen.render_section(SAMPLE_ARTIFACT)

    assert "blocked" in section
    assert "no ablation config-switch exists yet" in section


def test_render_section_marks_partial_cells_distinctly_from_blocked():
    section = gen.render_section(SAMPLE_ARTIFACT)

    assert "partial" in section


def test_splice_inserts_markers_into_an_empty_readme():
    section = gen.render_section(SAMPLE_ARTIFACT)
    result = gen.splice("", section)

    assert result == section
    assert gen.START_MARKER in result
    assert gen.END_MARKER in result


def test_splice_appends_to_existing_content_without_markers():
    section = gen.render_section(SAMPLE_ARTIFACT)
    result = gen.splice("# Traverse\n\nSome intro text.\n", section)

    assert result.startswith("# Traverse")
    assert "Some intro text." in result
    assert gen.START_MARKER in result


def test_splice_replaces_an_existing_section_leaving_the_rest_untouched():
    section_v1 = gen.render_section(SAMPLE_ARTIFACT)
    original = f"# Traverse\n\nIntro.\n\n{section_v1}\n\n## Other stuff\n"

    v2_artifact = {**SAMPLE_ARTIFACT, "run_id": "2026-10-01T000000Z"}
    section_v2 = gen.render_section(v2_artifact)
    result = gen.splice(original, section_v2)

    assert "2026-10-01T000000Z" in result
    assert "2026-09-28T000000Z" not in result
    assert "# Traverse" in result
    assert "Intro." in result
    assert "## Other stuff" in result


def test_splice_is_idempotent():
    section = gen.render_section(SAMPLE_ARTIFACT)
    once = gen.splice("# Traverse\n", section)
    twice = gen.splice(once, section)

    assert once == twice


def test_main_writes_the_readme_from_a_run_file(tmp_path, monkeypatch):
    run_path = tmp_path / "latest.json"
    run_path.write_text(json.dumps(SAMPLE_ARTIFACT))
    readme_path = tmp_path / "README.md"
    readme_path.write_text("# Traverse\n\nIntro.\n")

    monkeypatch.setattr(gen, "README_PATH", readme_path)
    monkeypatch.setattr(sys, "argv", ["publish_ablation_readme.py", "--run", str(run_path)])

    exit_code = gen.main()

    assert exit_code == 0
    content = readme_path.read_text()
    assert "# Traverse" in content
    assert gen.START_MARKER in content
    assert "0.700" in content


def test_main_fails_cleanly_when_no_run_exists(tmp_path, capsys):
    exit_code_argv = ["publish_ablation_readme.py", "--run", str(tmp_path / "missing.json")]
    original_argv = sys.argv
    sys.argv = exit_code_argv
    try:
        exit_code = gen.main()
    finally:
        sys.argv = original_argv

    assert exit_code == 1

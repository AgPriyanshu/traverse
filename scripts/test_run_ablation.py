"""Unit tests for the pure parts of scripts/run_ablation.py (S8.8).

No network, no DB: ``run_matrix``/``persist`` need a live API and Postgres
and are exercised by hand against the integration stack (see
plans/sprint-8/HANDOFF.md), same split as every other eval harness between
"logic that's testable in CI" and "the live run".
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_ablation import (
    _slugify_title,
    corpus_checksum,
    git_sha,
    load_cache,
    load_state,
    resolve_book_id,
    save_cache,
    save_state,
)


def test_git_sha_prefers_env_var(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "deadbeef")
    assert git_sha() == "deadbeef"


def test_git_sha_falls_back_to_git_command(monkeypatch):
    monkeypatch.delenv("GIT_SHA", raising=False)
    sha = git_sha()
    # Either a real 40-char SHA (host/CI has .git) or None (no git available,
    # e.g. inside the api container) -- never an exception either way.
    assert sha is None or len(sha) == 40


def test_corpus_checksum_reads_pdf_sha256():
    manifest = {"books": {"pride-and-prejudice": {"pdf_sha256": "abc123"}}}
    assert corpus_checksum(manifest, "pride-and-prejudice") == "abc123"


def test_corpus_checksum_missing_book_is_none():
    manifest = {"books": {}}
    assert corpus_checksum(manifest, "nonexistent") is None


def test_slugify_title_matches_relation_quality_convention():
    assert _slugify_title("Pride And Prejudice") == "pride-and-prejudice"
    assert _slugify_title("Wuthering Heights") == "wuthering-heights"


def test_resolve_book_id_matches_by_slug(monkeypatch):
    from scripts import run_ablation

    books = [
        {"id": "id-1", "title": "Pride And Prejudice", "ingested_at": "2026-01-01T00:00:00Z"},
        {"id": "id-2", "title": "Wuthering Heights", "ingested_at": "2026-01-02T00:00:00Z"},
    ]
    monkeypatch.setattr(run_ablation, "_get", lambda *a, **k: books)

    assert resolve_book_id("http://x", "pride-and-prejudice") == "id-1"
    assert resolve_book_id("http://x", "wuthering-heights") == "id-2"
    assert resolve_book_id("http://x", "no-such-book") is None


def test_resolve_book_id_picks_most_recently_ingested_on_duplicate_title(monkeypatch):
    from scripts import run_ablation

    books = [
        {"id": "old", "title": "Pride And Prejudice", "ingested_at": "2026-01-01T00:00:00Z"},
        {"id": "new", "title": "Pride And Prejudice", "ingested_at": "2026-06-01T00:00:00Z"},
    ]
    monkeypatch.setattr(run_ablation, "_get", lambda *a, **k: books)

    assert resolve_book_id("http://x", "pride-and-prejudice") == "new"


def test_state_roundtrip(tmp_path):
    state_path = tmp_path / "run" / "state.json"
    assert load_state(state_path) == {}

    save_state(state_path, {"extraction:foo": {"status": "done", "results": []}})
    reloaded = load_state(state_path)

    assert reloaded == {"extraction:foo": {"status": "done", "results": []}}


def test_cache_roundtrip(tmp_path, monkeypatch):
    from scripts import run_ablation

    monkeypatch.setattr(run_ablation, "CACHE_DIR", tmp_path / "cache")

    assert load_cache("abc123") is None
    save_cache("abc123", {"status": "measured", "metrics": {"f1": 0.7}})

    assert load_cache("abc123") == {"status": "measured", "metrics": {"f1": 0.7}}

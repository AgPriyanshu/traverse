"""Load gold rosters and pin them to the live corpus manifest checksum.

A gold roster's page-level labels are only valid against the exact PDF they
were labelled from (S2.16's deterministic pagination, SCR-1's heading-font
fix). Re-running ``scripts/seed_corpus.py`` with different layout constants
regenerates a different ``pdf_sha256``, and every ``first_page`` label
silently stops meaning anything -- so a checksum mismatch fails the eval run
loudly rather than scoring against a corpus the labels no longer describe.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLD_DIR = REPO_ROOT / "eval" / "gold"
SCHEMA_PATH = REPO_ROOT / "eval" / "schema" / "roster.schema.json"
RELATIONS_SCHEMA_PATH = REPO_ROOT / "eval" / "schema" / "relations.schema.json"
MANIFEST_PATH = REPO_ROOT / "corpus" / "manifest.json"


class CorpusChecksumMismatch(RuntimeError):
    """A gold roster's pinned PDF checksum no longer matches the live corpus."""


class RosterSchemaError(RuntimeError):
    """A gold roster does not match ``eval/schema/roster.schema.json``."""


def _load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text())


def validate_roster(roster: dict[str, Any]) -> None:
    """Raise `RosterSchemaError` if `roster` does not match the gold schema."""
    validator = Draft202012Validator(_load_schema())
    errors = sorted(validator.iter_errors(roster), key=lambda e: list(e.path))
    if errors:
        detail = "; ".join(f"{list(e.path)}: {e.message}" for e in errors)

        raise RosterSchemaError(f"{SCHEMA_PATH.name} violations: {detail}")


def gold_roster_path(book_key: str) -> Path:
    slug = book_key.replace("-", "_")
    return GOLD_DIR / slug / "roster.yaml"


def load_gold_roster(book_key: str, *, verify_checksum: bool = True) -> dict[str, Any]:
    """Load and schema-validate one book's gold roster.

    Args:
        book_key: A key under ``corpus/manifest.json``'s ``books`` (hyphenated,
            e.g. ``pride-and-prejudice``).
        verify_checksum: Set False only for tests that intentionally exercise
            a stale fixture -- every real eval run must verify.

    Returns:
        The parsed, schema-valid roster document.

    Raises:
        FileNotFoundError: If no gold roster exists for ``book_key`` yet.
        RosterSchemaError: If the roster does not match the schema.
        CorpusChecksumMismatch: If ``verify_checksum`` and the corpus has been
            repaginated since this roster was labelled.
    """
    path = gold_roster_path(book_key)
    if not path.exists():
        raise FileNotFoundError(
            f"no gold roster for {book_key!r} at {path.relative_to(REPO_ROOT)}"
        )

    roster = yaml.safe_load(path.read_text())
    validate_roster(roster)

    if verify_checksum:
        _verify_corpus_checksum(book_key, roster)

    return roster


def _verify_corpus_checksum(book_key: str, roster: dict[str, Any]) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text())
    live = manifest.get("books", {}).get(book_key)
    if live is None:
        raise CorpusChecksumMismatch(
            f"{book_key!r} is not in {MANIFEST_PATH.relative_to(REPO_ROOT)} -- "
            "run `make seed` before scoring."
        )

    pinned = roster["corpus_pdf_sha256"]
    actual = live["pdf_sha256"]
    if pinned != actual:
        raise CorpusChecksumMismatch(
            f"{book_key!r} gold roster pinned to pdf_sha256={pinned[:12]}... but "
            f"the corpus manifest now has {actual[:12]}... -- the corpus was "
            "regenerated (repaginated) since this roster was labelled. Re-run "
            "scripts/label_roster.py to re-pin page numbers before trusting any "
            "score against this roster."
        )

    if roster["page_count"] != live["page_count"]:
        raise CorpusChecksumMismatch(
            f"{book_key!r} gold roster pinned to page_count={roster['page_count']} "
            f"but the corpus manifest now has {live['page_count']} -- repagination "
            "changed the page count."
        )


def available_gold_books() -> list[str]:
    """List book keys with a gold roster on disk, without validating them."""
    if not GOLD_DIR.exists():
        return []

    return sorted(
        p.parent.name.replace("_", "-") for p in GOLD_DIR.glob("*/roster.yaml")
    )


def gold_relations_path(book_key: str) -> Path:
    slug = book_key.replace("-", "_")
    return GOLD_DIR / slug / "relations.yaml"


def load_gold_relations(
    book_key: str, *, verify_checksum: bool = True
) -> dict[str, Any]:
    """Load and schema-validate one book's gold relations (S4.14).

    Pinned to the corpus checksum like the roster, and every named character
    must exist in that book's gold roster, so a rename in one file cannot
    silently orphan the other.

    Raises:
        FileNotFoundError: If no gold relations exist for ``book_key`` yet.
        RosterSchemaError: If the file does not match its schema or names an
            unknown character.
        CorpusChecksumMismatch: If ``verify_checksum`` and the corpus has been
            repaginated since labelling.
    """
    path = gold_relations_path(book_key)
    if not path.exists():
        raise FileNotFoundError(
            f"no gold relations for {book_key!r} at {path.relative_to(REPO_ROOT)}"
        )

    document = yaml.safe_load(path.read_text())
    schema = json.loads(RELATIONS_SCHEMA_PATH.read_text())
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document), key=lambda e: list(e.path)
    )
    if errors:
        detail = "; ".join(f"{list(e.path)}: {e.message}" for e in errors)

        raise RosterSchemaError(f"{RELATIONS_SCHEMA_PATH.name} violations: {detail}")

    roster = load_gold_roster(book_key, verify_checksum=verify_checksum)
    known = {c["canonical_name"] for c in roster["characters"]}
    unknown = sorted(
        {
            name
            for relation in document["relations"]
            for name in (relation["subject"], relation["object"])
            if name not in known
        }
    )
    if unknown:
        raise RosterSchemaError(f"relations name characters not in the roster: {unknown}")

    if verify_checksum:
        _verify_corpus_checksum(book_key, document)

    return document

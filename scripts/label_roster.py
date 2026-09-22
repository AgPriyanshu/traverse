#!/usr/bin/env python3
"""Terminal review tool for gold character rosters (S3.13).

Labelling a roster by hand from scratch is a week's work no sprint has.
Instead this walks a list of *candidates* — either the system's own pass-1
output (once `api/extraction/**` lands and can be dumped to JSON, or read
live from `GET /projects/{id}/characters` + `/characters/{id}/mentions`) or
a seed drafted from a public-domain reference (a Gutenberg character index, a
published concordance) — and asks a human to confirm, correct, split or
reject each one, writing the result as a schema-valid, checksum-pinned
`eval/gold/<book>/roster.yaml`.

Reviewing 60 pre-populated characters takes an hour; labelling 60 characters
blind takes a day. The review loop (`review_candidates`) takes plain dicts in
and returns plain dicts out with no I/O of its own, so it is unit-testable by
injecting a scripted `input_fn` — and reusable, unchanged, for Sprint 8's
question-set review (a different candidate shape, the same
confirm/edit/split/reject loop).

Usage:
    python3 scripts/label_roster.py validate --book pride-and-prejudice
    python3 scripts/label_roster.py repin --book pride-and-prejudice
    python3 scripts/label_roster.py review --book pride-and-prejudice \\
        --candidates path/to/pass1_output.json
    python3 scripts/label_roster.py review --book pride-and-prejudice \\
        --api-base-url http://localhost:8000 --project-id <uuid>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eval.loaders import (  # noqa: E402
    CorpusChecksumMismatch,
    RosterSchemaError,
    gold_roster_path,
    load_gold_roster,
)

MANIFEST_PATH = REPO_ROOT / "corpus" / "manifest.json"

_TIERS = ("protagonist", "major", "minor", "mentioned")


@dataclass
class Candidate:
    """One system-proposed (or hand-seeded) character, before human review."""

    canonical_name: str
    aliases: list[str] = field(default_factory=list)
    importance_tier: str = "mentioned"
    first_page: int | None = None


def load_candidates_from_json(path: Path) -> list[Candidate]:
    """Load a flat JSON array of candidate dicts (the pass-1 dump shape)."""
    raw = json.loads(path.read_text())

    return [
        Candidate(
            canonical_name=item["canonical_name"],
            aliases=list(item.get("aliases", [])),
            importance_tier=item.get("importance_tier", "mentioned"),
            first_page=item.get("first_page"),
        )
        for item in raw
    ]


def load_candidates_from_api(
    base_url: str, project_id: str, book_key: str, *, timeout: float = 10.0
) -> list[Candidate]:
    """Pull candidates from the live `GET /projects/{id}/characters` contract.

    Only available once be2's S3.6 route is serving real data; raises the
    underlying HTTP error rather than guessing at a shape if it isn't.
    """
    import urllib.request

    url = f"{base_url.rstrip('/')}/api/projects/{project_id}/characters"
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        payload = json.loads(response.read())

    return [
        Candidate(
            canonical_name=item["canonical_name"],
            aliases=list(item.get("aliases", [])),
            importance_tier=item.get("importance_tier", "mentioned"),
            first_page=item.get("first_page"),
        )
        for item in payload
        if item.get("book_key", book_key) == book_key
    ]


def _prompt(input_fn: Callable[[str], str], message: str, *, default: str = "") -> str:
    raw = input_fn(f"{message} ").strip()

    return raw if raw else default


def review_candidates(
    candidates: Iterable[Candidate],
    *,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Walk `candidates`, asking a human to confirm/edit/split/reject each.

    Returns:
        ``(characters, rejected_non_characters)`` in the gold-schema shape.

    Per-candidate commands (read from `input_fn`, so a test can script a
    whole session as an iterator's worth of canned answers):
        c   confirm as-is
        e   edit canonical_name / aliases / tier / first_page, then confirm
        s   split: keep this candidate, then define one more from scratch
        r   reject (prompts for a reason)
        skip anything else — leaves the candidate out of both lists, for a
            duplicate the reviewer wants to handle under a different entry
    """
    characters: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for candidate in candidates:
        print_fn(
            f"\n{candidate.canonical_name!r} aliases={candidate.aliases} "
            f"tier={candidate.importance_tier} first_page={candidate.first_page}"
        )
        action = _prompt(
            input_fn, "[c]onfirm / [e]dit / [s]plit / [r]eject / [skip]?", default="c"
        ).lower()

        if action.startswith("r"):
            reason = _prompt(
                input_fn, "Reason for rejection:", default="not a character"
            )
            rejected.append(
                {"surface_form": candidate.canonical_name, "reason": reason}
            )
            continue

        if action.startswith("skip"):
            continue

        entry = _candidate_to_entry(candidate)
        if action.startswith("e"):
            entry = _edit_entry(entry, input_fn, print_fn)
        characters.append(entry)

        if action.startswith("s"):
            print_fn("Define the split-off character:")
            extra = _prompt_new_entry(input_fn)
            characters.append(extra)

    return characters, rejected


def _candidate_to_entry(candidate: Candidate) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "canonical_name": candidate.canonical_name,
        "aliases": list(candidate.aliases),
        "importance_tier": candidate.importance_tier,
    }
    if candidate.first_page is not None:
        entry["first_page"] = candidate.first_page

    return entry


def _edit_entry(
    entry: dict[str, Any],
    input_fn: Callable[[str], str],
    print_fn: Callable[[str], None],
) -> dict[str, Any]:
    entry["canonical_name"] = _prompt(
        input_fn,
        f"canonical_name [{entry['canonical_name']}]:",
        default=entry["canonical_name"],
    )
    aliases_raw = _prompt(
        input_fn,
        f"aliases, comma-separated [{', '.join(entry['aliases'])}]:",
        default=", ".join(entry["aliases"]),
    )
    entry["aliases"] = [a.strip() for a in aliases_raw.split(",") if a.strip()]
    tier = _prompt(
        input_fn,
        f"importance_tier {_TIERS} [{entry['importance_tier']}]:",
        default=entry["importance_tier"],
    )
    if tier not in _TIERS:
        print_fn(
            f"  {tier!r} is not one of {_TIERS}; keeping {entry['importance_tier']!r}."
        )
    else:
        entry["importance_tier"] = tier
    page_raw = _prompt(
        input_fn,
        f"first_page [{entry.get('first_page', '')}]:",
        default=str(entry.get("first_page", "")),
    )
    if page_raw.strip():
        entry["first_page"] = int(page_raw)

    return entry


def _prompt_new_entry(input_fn: Callable[[str], str]) -> dict[str, Any]:
    name = _prompt(input_fn, "  canonical_name:")
    aliases_raw = _prompt(input_fn, "  aliases, comma-separated:")
    tier = _prompt(input_fn, f"  importance_tier {_TIERS}:", default="mentioned")
    page_raw = _prompt(input_fn, "  first_page:")
    entry: dict[str, Any] = {
        "canonical_name": name,
        "aliases": [a.strip() for a in aliases_raw.split(",") if a.strip()],
        "importance_tier": tier if tier in _TIERS else "mentioned",
    }
    if page_raw.strip():
        entry["first_page"] = int(page_raw)

    return entry


def write_roster(
    book_key: str,
    characters: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    *,
    labelled_by: str,
    source_notes: str = "",
) -> Path:
    """Validate and write ``eval/gold/<book>/roster.yaml``, pinned to the
    live corpus manifest checksum — never to a stale one a reviewer forgot to
    refresh."""
    manifest = json.loads(MANIFEST_PATH.read_text())
    live = manifest.get("books", {}).get(book_key)
    if live is None:
        raise SystemExit(
            f"{book_key!r} is not in {MANIFEST_PATH} -- run `make seed` first."
        )

    roster = {
        "book_key": book_key,
        "corpus_pdf_sha256": live["pdf_sha256"],
        "page_count": live["page_count"],
        "labelled_by": labelled_by,
        "labelled_at": datetime.now(UTC).isoformat(),
        "source_notes": source_notes,
        "characters": characters,
        "rejected_non_characters": rejected,
    }

    from eval.loaders import validate_roster

    validate_roster(roster)

    path = gold_roster_path(book_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(roster, sort_keys=False, allow_unicode=True))

    return path


def cmd_validate(args: argparse.Namespace) -> None:
    roster = load_gold_roster(args.book, verify_checksum=not args.no_checksum)
    print(
        f"OK: {args.book} -- {len(roster['characters'])} characters, "
        f"{len(roster.get('rejected_non_characters', []))} rejected entries, "
        f"pinned to pdf_sha256={roster['corpus_pdf_sha256'][:12]}..."
    )


def cmd_repin(args: argparse.Namespace) -> None:
    """Re-pin an existing roster's checksum/page_count to the live corpus.

    For a *deliberate* re-pagination only -- this does not re-verify any
    first_page value still makes sense, it only stops the loud checksum
    failure. Re-review the roster's page numbers before trusting them again.
    """
    path = gold_roster_path(args.book)
    roster = yaml.safe_load(path.read_text())
    manifest = json.loads(MANIFEST_PATH.read_text())
    live = manifest["books"][args.book]
    roster["corpus_pdf_sha256"] = live["pdf_sha256"]
    roster["page_count"] = live["page_count"]
    path.write_text(yaml.safe_dump(roster, sort_keys=False, allow_unicode=True))
    print(f"re-pinned {path} to pdf_sha256={live['pdf_sha256'][:12]}...")


def cmd_review(args: argparse.Namespace) -> None:
    if args.candidates:
        candidates = load_candidates_from_json(Path(args.candidates))
    elif args.api_base_url and args.project_id:
        candidates = load_candidates_from_api(
            args.api_base_url, args.project_id, args.book
        )
    else:
        candidates = []
        print("No --candidates/--api-base-url given -- starting from an empty list.")
        print("Define characters from scratch; type an empty canonical_name to stop.")
        while True:
            entry = _prompt_new_entry(input)
            if not entry["canonical_name"]:
                break
            candidates.append(
                Candidate(
                    entry["canonical_name"],
                    entry["aliases"],
                    entry["importance_tier"],
                    entry.get("first_page"),
                )
            )

    characters, rejected = review_candidates(candidates)
    if not characters:
        print("Nothing confirmed -- not writing a roster.")
        return

    path = write_roster(
        args.book,
        characters,
        rejected,
        labelled_by=args.labelled_by,
        source_notes=args.notes,
    )
    print(f"wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser(
        "validate", help="Schema- and checksum-check a gold roster."
    )
    p_validate.add_argument("--book", required=True)
    p_validate.add_argument("--no-checksum", action="store_true")
    p_validate.set_defaults(func=cmd_validate)

    p_repin = sub.add_parser(
        "repin", help="Re-pin a roster's checksum after a deliberate re-seed."
    )
    p_repin.add_argument("--book", required=True)
    p_repin.set_defaults(func=cmd_repin)

    p_review = sub.add_parser(
        "review", help="Interactively build/update a gold roster."
    )
    p_review.add_argument("--book", required=True)
    p_review.add_argument(
        "--candidates", help="Path to a JSON array of pass-1 candidates."
    )
    p_review.add_argument("--api-base-url")
    p_review.add_argument("--project-id")
    p_review.add_argument(
        "--labelled-by", default="human review (scripts/label_roster.py)"
    )
    p_review.add_argument("--notes", default="")
    p_review.set_defaults(func=cmd_review)

    args = parser.parse_args()
    try:
        args.func(args)
    except (RosterSchemaError, CorpusChecksumMismatch, FileNotFoundError) as exc:
        raise SystemExit(f"error: {exc}") from exc


if __name__ == "__main__":
    main()

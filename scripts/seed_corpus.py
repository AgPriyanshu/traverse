#!/usr/bin/env python3
"""Fetch, license and paginate the Sprint 2 demo corpus (devops-1.md S2.16).

Downloads the plain-text Project Gutenberg edition of each PRD §7 novel,
strips the Gutenberg header/footer, and repaginates the body into a PDF using
a hand-rolled, dependency-free writer (stdlib only — no pandoc, no calibre, no
pypdf) so `make seed` never needs a network-installed tool.

Pagination is a pure function of the stripped text and the layout constants
below (fixed page size, fixed-pitch Courier, fixed chars-per-line and
lines-per-page). That determinism is the point, not an implementation detail:
a chunk's citation is a page number, `api/tests/fixtures/chapter_truth/*.json`
(be1, S2.3) hand-labels chapter boundaries against these exact page numbers,
and a corpus that repaginates differently on every run invalidates every
labelled eval answer from Sprint 8 (see devops-1.md S2.16 and BRANCH.md's
"DO NOT re-run download_models()" spirit — don't silently regenerate history
out from under another agent's fixtures).

Usage:
    python3 scripts/seed_corpus.py            # fetch + build everything, idempotent
    python3 scripts/seed_corpus.py --force    # re-download and re-build anyway
    python3 scripts/seed_corpus.py --only pride-and-prejudice,frankenstein

Output:
    corpus/downloads/<key>.txt   the stripped Gutenberg source (gitignored)
    corpus/downloads/<key>.pdf   the paginated novel (gitignored)
    corpus/manifest.json         pinned source URL, licence, SHA-256s, page
                                  count and the exact command that built it
                                  (committed — this is ETH-1 evidence)
    corpus/LICENSES.md           human-readable table of the same (committed)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = REPO_ROOT / "corpus"
DOWNLOADS_DIR = CORPUS_DIR / "downloads"
MANIFEST_PATH = CORPUS_DIR / "manifest.json"
LICENSES_PATH = CORPUS_DIR / "LICENSES.md"

CONVERSION_COMMAND = "python3 scripts/seed_corpus.py"

# Fixed PDF layout. Changing any of these repaginates every book already
# built — bump a comment here and regenerate `manifest.json` deliberately,
# never as a side effect of an unrelated change.
PAGE_WIDTH_PT = 612  # US Letter
PAGE_HEIGHT_PT = 792
MARGIN_PT = 72
FONT_SIZE_PT = 10
LEADING_PT = 12
# Courier is fixed-pitch at exactly 600/1000 em in every standard PDF viewer,
# so character-count wrapping is exact with no font metrics library needed.
_COURIER_CHAR_WIDTH_PT = FONT_SIZE_PT * 0.6
CHARS_PER_LINE = int((PAGE_WIDTH_PT - 2 * MARGIN_PT) / _COURIER_CHAR_WIDTH_PT)
LINES_PER_PAGE = int((PAGE_HEIGHT_PT - 2 * MARGIN_PT) / LEADING_PT)

GUTENBERG_TXT_URL = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt"

_START_MARKER_RE = re.compile(
    r"^\*\*\*\s*START OF THE PROJECT GUTENBERG EBOOK.*\*\*\*\s*$", re.IGNORECASE
)
_END_MARKER_RE = re.compile(
    r"^\*\*\*\s*END OF THE PROJECT GUTENBERG EBOOK.*\*\*\*\s*$", re.IGNORECASE
)


@dataclass(frozen=True)
class CorpusBook:
    key: str
    title: str
    author: str
    gutenberg_id: int
    why: str  # PRD §7's reason this title is in the set — carried into LICENSES.md.


# The PRD §7 set (devops-1.md S2.16 table), keyed by Project Gutenberg ebook id.
CORPUS: list[CorpusBook] = [
    CorpusBook(
        "pride-and-prejudice",
        "Pride and Prejudice",
        "Jane Austen",
        1342,
        "dense, checkable family network; the aggregation test",
    ),
    CorpusBook(
        "wuthering-heights",
        "Wuthering Heights",
        "Emily Bronte",
        768,
        "the name-collision regression case",
    ),
    CorpusBook(
        "frankenstein",
        "Frankenstein; or, the Modern Prometheus",
        "Mary Wollstonecraft Shelley",
        84,
        "nested framing -> assertion provenance",
    ),
    CorpusBook(
        "the-great-gatsby",
        "The Great Gatsby",
        "F. Scott Fitzgerald",
        64317,
        "first-person narrator who is a character",
    ),
    CorpusBook(
        "anna-karenina",
        "Anna Karenina",
        "Leo Tolstoy",
        1399,
        "scale + patronymics/diminutives stress case",
    ),
]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def fetch(book: CorpusBook, *, force: bool = False) -> Path:
    """Download the plain-text Gutenberg edition, or reuse it if already present."""
    destination = DOWNLOADS_DIR / f"{book.key}.txt"
    if destination.exists() and destination.stat().st_size > 0 and not force:
        print(f"have    {destination.relative_to(REPO_ROOT)}")
        return destination

    url = GUTENBERG_TXT_URL.format(id=book.gutenberg_id)
    print(f"fetch   {url}")
    data: bytes | None = None
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = response.read()
            break
        except (urllib.error.URLError, OSError) as exc:
            last_error = exc
            print(f"  retry {attempt}/3 after {exc!r}")
    if data is None:
        raise RuntimeError(f"could not fetch {url}") from last_error

    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return destination


def strip_boilerplate(raw_text: str) -> str:
    """Drop the Gutenberg legal header/footer, keeping only the novel's body."""
    lines = raw_text.splitlines()
    start_idx = 0
    end_idx = len(lines)
    for i, line in enumerate(lines):
        if _START_MARKER_RE.match(line.strip()):
            start_idx = i + 1
        if _END_MARKER_RE.match(line.strip()):
            end_idx = i
            break

    body = "\n".join(lines[start_idx:end_idx]).strip("\n")
    if not body:
        raise ValueError(
            "Gutenberg START/END markers not found — boilerplate stripping failed; "
            "the source format may have changed."
        )
    return body


def paginate(text: str) -> list[list[str]]:
    """Wrap `text` into fixed-width lines, then group lines into fixed-height pages.

    A pure function of `text` and the module-level layout constants: the same
    source always produces the same page boundaries.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = re.split(r"\n\s*\n", normalized)

    lines: list[str] = []
    for paragraph in paragraphs:
        collapsed = " ".join(paragraph.split())
        if not collapsed:
            continue
        lines.extend(textwrap.wrap(collapsed, width=CHARS_PER_LINE) or [""])
        lines.append("")  # blank line between paragraphs, incl. chapter headings

    while lines and lines[-1] == "":
        lines.pop()

    if not lines:
        return [[]]

    return [lines[i : i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)]


def _escape_pdf_text(line: str) -> bytes:
    # The 14 standard PDF fonts have no embedded glyph table, so anything
    # outside WinAnsiEncoding (~cp1252) has no glyph to show; replace rather
    # than crash the whole build over one curly quote in one novel.
    encoded = line.encode("cp1252", errors="replace")
    return encoded.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def build_pdf(pages: list[list[str]]) -> bytes:
    """Emit a minimal, uncompressed multi-page PDF using only the base-14 Courier font.

    No embedded fonts, no compression, no third-party library — this script's
    only dependency is the standard library, so `make seed` never needs
    pandoc/calibre/wkhtmltopdf installed.
    """
    catalog_num, pages_num, font_num = 1, 2, 3
    first_page_obj = 4  # page k -> first_page_obj + 2k ; its content -> +1

    objects: dict[int, bytes] = {
        catalog_num: f"<< /Type /Catalog /Pages {pages_num} 0 R >>".encode(),
        font_num: (
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier "
            b"/Encoding /WinAnsiEncoding >>"
        ),
    }

    kids = " ".join(f"{first_page_obj + 2 * k} 0 R" for k in range(len(pages)))
    objects[pages_num] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode()
    )

    top_y = PAGE_HEIGHT_PT - MARGIN_PT
    for k, page_lines in enumerate(pages):
        page_obj = first_page_obj + 2 * k
        content_obj = page_obj + 1

        parts = [
            b"BT",
            f"/F1 {FONT_SIZE_PT} Tf".encode(),
            f"{LEADING_PT} TL".encode(),
            f"{MARGIN_PT} {top_y} Td".encode(),
        ]
        for i, line in enumerate(page_lines):
            if i > 0:
                parts.append(b"T*")
            parts.append(b"(" + _escape_pdf_text(line) + b") Tj")
        parts.append(b"ET")
        stream = b"\n".join(parts)

        objects[content_obj] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )
        objects[page_obj] = (
            f"<< /Type /Page /Parent {pages_num} 0 R "
            f"/MediaBox [0 0 {PAGE_WIDTH_PT} {PAGE_HEIGHT_PT}] "
            f"/Resources << /Font << /F1 {font_num} 0 R >> >> "
            f"/Contents {content_obj} 0 R >>"
        ).encode()

    max_obj = max(objects)
    buf = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for num in range(1, max_obj + 1):
        offsets[num] = len(buf)
        buf += f"{num} 0 obj\n".encode() + objects[num] + b"\nendobj\n"

    xref_offset = len(buf)
    buf += f"xref\n0 {max_obj + 1}\n".encode()
    buf += b"0000000000 65535 f \n"
    for num in range(1, max_obj + 1):
        buf += f"{offsets[num]:010d} 00000 n \n".encode()

    buf += f"trailer\n<< /Size {max_obj + 1} /Root {catalog_num} 0 R >>\n".encode()
    buf += f"startxref\n{xref_offset}\n%%EOF".encode()

    return bytes(buf)


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {"generated_at": None, "books": {}}


def save_manifest(manifest: dict) -> None:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def write_licenses_md(manifest: dict) -> None:
    lines = [
        "# Corpus licenses",
        "",
        "Every text below is in the public domain in the United States and is",
        "distributed by [Project Gutenberg](https://www.gutenberg.org) under the",
        "[Project Gutenberg License](https://www.gutenberg.org/policy/license.html):",
        "free to copy and redistribute provided the Gutenberg header/footer travels",
        "with it, or the redistribution is clearly marked as altered. This corpus",
        "strips that header/footer and repaginates the text — this file is that",
        "notice.",
        "",
        "Regenerate with `make seed`. `corpus/manifest.json` pins the exact source",
        "URL, SHA-256 of both the source text and the built PDF, page count and",
        "conversion command each entry below was built with — a citation in a",
        "labelled eval answer (Sprint 8) is a page number, and a silently",
        "regenerated corpus with different pagination invalidates it.",
        "",
        "| Title | Author | Gutenberg ID | Pages | Source SHA-256 | Why (PRD §7) |",
        "|---|---|---|---|---|---|",
    ]

    by_key = {book.key: book for book in CORPUS}
    for key in sorted(manifest["books"]):
        record = manifest["books"][key]
        why = by_key[key].why if key in by_key else ""
        lines.append(
            f"| {record['title']} | {record['author']} | {record['gutenberg_id']} | "
            f"{record['page_count']} | `{record['source_sha256'][:12]}…` | {why} |"
        )
    lines.append("")

    LICENSES_PATH.write_text("\n".join(lines) + "\n")


def process_book(book: CorpusBook, *, force: bool) -> dict:
    source_path = fetch(book, force=force)
    source_sha256 = sha256_of(source_path)

    pdf_path = DOWNLOADS_DIR / f"{book.key}.pdf"
    manifest = load_manifest()
    existing = manifest["books"].get(book.key)

    checksum_verified = (
        not force
        and existing is not None
        and existing.get("source_sha256") == source_sha256
        and pdf_path.exists()
        and sha256_of(pdf_path) == existing.get("pdf_sha256")
    )
    if checksum_verified:
        print(f"skip    {book.key} (unchanged, checksum-verified)")
        return existing  # type: ignore[return-value]

    raw_text = source_path.read_text(encoding="utf-8", errors="replace")
    body = strip_boilerplate(raw_text)
    pages = paginate(body)
    pdf_bytes = build_pdf(pages)
    pdf_path.write_bytes(pdf_bytes)

    record = {
        "title": book.title,
        "author": book.author,
        "gutenberg_id": book.gutenberg_id,
        "source_url": GUTENBERG_TXT_URL.format(id=book.gutenberg_id),
        "license": "Public Domain (Project Gutenberg)",
        "source_sha256": source_sha256,
        "pdf_sha256": sha256_of(pdf_path),
        "page_count": len(pages),
        "conversion_command": CONVERSION_COMMAND,
        "layout": {
            "page_size_pt": [PAGE_WIDTH_PT, PAGE_HEIGHT_PT],
            "margin_pt": MARGIN_PT,
            "font": "Courier",
            "font_size_pt": FONT_SIZE_PT,
            "chars_per_line": CHARS_PER_LINE,
            "lines_per_page": LINES_PER_PAGE,
        },
        "pdf_path": str(pdf_path.relative_to(REPO_ROOT)),
        "built_at": datetime.now(UTC).isoformat(),
    }
    manifest["books"][book.key] = record
    manifest["generated_at"] = datetime.now(UTC).isoformat()
    save_manifest(manifest)

    print(
        f"built   {pdf_path.relative_to(REPO_ROOT)} "
        f"({len(pages)} pages, sha256 {record['pdf_sha256'][:12]}…)"
    )
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download and re-build even if checksums already match.",
    )
    parser.add_argument(
        "--only",
        help="Comma-separated corpus keys to process (default: all five).",
    )
    args = parser.parse_args()

    wanted = set(args.only.split(",")) if args.only else None
    books = [book for book in CORPUS if wanted is None or book.key in wanted]
    if not books:
        raise SystemExit(f"--only matched nothing in {sorted(b.key for b in CORPUS)}")

    for book in books:
        process_book(book, force=args.force)

    write_licenses_md(load_manifest())

    print()
    print(f"Corpus in {DOWNLOADS_DIR.relative_to(REPO_ROOT)}")
    print(f"Manifest: {MANIFEST_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()

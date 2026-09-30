from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from uuid import UUID

from eval.identity_metrics import (
    Appearance,
    canonical_graph_checksum,
    score_identity_links,
)
from eval.loaders import CorpusChecksumMismatch, RosterSchemaError, load_gold_identity
from eval.metrics import CharacterCluster, match_rosters
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..db.models import Book, Character, CharacterAppearance, Project, Relation

MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent.parent / "corpus" / "manifest.json"
)


def _slugify_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _load_manifest_books() -> dict:
    if not MANIFEST_PATH.exists():
        return {}

    return json.loads(MANIFEST_PATH.read_text()).get("books", {})


class ReconciliationQualityOut(BaseModel):
    project_id: UUID
    series_key: str | None = None
    gold_available: bool
    error: str | None = None

    link_precision: float | None = None
    link_recall: float | None = None
    false_merge_rate: float | None = None
    duplicate_rate: float | None = None

    linked_pairs: int = 0
    correctly_linked_pairs: int = 0
    false_merge_pairs: int = 0
    gold_linked_pairs: int = 0
    missed_link_pairs: int = 0
    duplicate_characters: int = 0
    gold_multi_book_characters: int = 0

    character_count: int = 0
    book_count: int = 0
    graph_checksum: str | None = None


def _detect_series_key(book_titles: list[str], manifest_books: dict) -> str | None:
    for title in book_titles:
        entry = manifest_books.get(_slugify_title(title))
        if entry and entry.get("series_key"):
            return entry["series_key"]

    return None


async def compute_reconciliation_quality(
    session: SQLModelAsyncSession, project_id: UUID
) -> ReconciliationQualityOut:
    """Score one project's cross-book character identity against gold.

    Returns ``gold_available=False`` (not an error) for a project whose books
    don't match a known series, or a series without a labelled gold set yet
    (today, every series except Anne of Green Gables, S5.14). The graph
    checksum is still reported in that case: order-independence does not
    need gold, only two projects to compare (``eval/runners/
    reconciliation.py --compare-project-id``).
    """
    project = await session.get(Project, project_id)
    if project is None:
        return ReconciliationQualityOut(
            project_id=project_id, gold_available=False, error="project not found"
        )

    books = (
        (
            await session.execute(
                select(Book)
                .where(Book.project_id == project_id)  # type: ignore[arg-type]
                .order_by(Book.series_order)
            )
        )
        .scalars()
        .all()
    )
    characters = (
        (
            await session.execute(
                select(Character).where(Character.project_id == project_id)  # type: ignore[arg-type]
            )
        )
        .scalars()
        .all()
    )
    relations = (
        (
            await session.execute(
                select(Relation).where(Relation.project_id == project_id)  # type: ignore[arg-type]
            )
        )
        .scalars()
        .all()
    )
    name_by_character_id = {c.id: c.canonical_name for c in characters}

    def _name(character_id: UUID | None) -> str:
        return name_by_character_id.get(character_id, str(character_id))

    checksum = canonical_graph_checksum(
        [(c.canonical_name, str(c.importance_tier)) for c in characters],
        [
            (_name(r.subject_character_id), r.predicate, _name(r.object_character_id))
            for r in relations
        ],
    )
    base = {
        "character_count": len(characters),
        "book_count": len(books),
        "graph_checksum": checksum,
    }

    manifest_books = _load_manifest_books()
    series_key = _detect_series_key([b.title for b in books], manifest_books)
    if series_key is None:
        return ReconciliationQualityOut(
            project_id=project_id,
            gold_available=False,
            error="project's books don't match a known series in corpus/manifest.json",
            **base,
        )

    try:
        document = load_gold_identity(series_key)
    except FileNotFoundError:
        return ReconciliationQualityOut(
            project_id=project_id, series_key=series_key, gold_available=False, **base
        )
    except (RosterSchemaError, CorpusChecksumMismatch) as exc:
        return ReconciliationQualityOut(
            project_id=project_id,
            series_key=series_key,
            gold_available=False,
            error=str(exc),
            **base,
        )

    book_key_by_order = {b["book_order"]: b["book_key"] for b in document["books"]}
    book_id_by_order: dict[int, UUID] = {
        book.series_order: book.id
        for book in books
        if book.series_order in book_key_by_order
        and _slugify_title(book.title) == book_key_by_order[book.series_order]
    }

    appearance_rows = []
    if book_id_by_order:
        appearance_rows = (
            await session.execute(
                select(CharacterAppearance, Character)
                .join(Character, Character.id == CharacterAppearance.character_id)  # type: ignore[arg-type]
                .where(CharacterAppearance.book_id.in_(book_id_by_order.values()))  # type: ignore[attr-defined]
            )
        ).all()

    order_by_book_id = {book_id: order for order, book_id in book_id_by_order.items()}
    appearances_by_book: dict[int, list[tuple[CharacterAppearance, Character]]] = (
        defaultdict(list)
    )
    for appearance, character in appearance_rows:
        order = order_by_book_id.get(appearance.book_id)
        if order is not None:
            appearances_by_book[order].append((appearance, character))

    gold_appearances = [
        Appearance(key=f"{c['canonical']}:{order}", cluster=c["canonical"])
        for c in document["characters"]
        for order in c["appears_in"]
    ]

    predicted_appearances: list[Appearance] = []
    for order, rows in appearances_by_book.items():
        gold_in_book = [
            CharacterCluster(
                id=c["canonical"],
                canonical_name=c["canonical"],
                aliases=tuple(c["surface_forms"].get(str(order), [])),
            )
            for c in document["characters"]
            if order in c["appears_in"]
        ]
        predicted_in_book = [
            CharacterCluster(
                id=str(character.id),
                canonical_name=character.canonical_name,
                aliases=tuple(appearance.surface_forms),
            )
            for appearance, character in rows
        ]
        match = match_rosters(gold_in_book, predicted_in_book)
        predicted_appearances.extend(
            Appearance(key=f"{m.gold_id}:{order}", cluster=m.predicted_id)
            for m in match.matches
        )

    scores = score_identity_links(gold_appearances, predicted_appearances)

    return ReconciliationQualityOut(
        project_id=project_id,
        series_key=series_key,
        gold_available=True,
        link_precision=scores.precision,
        link_recall=scores.recall,
        false_merge_rate=scores.false_merge_rate,
        duplicate_rate=scores.duplicate_rate,
        linked_pairs=scores.linked_pairs,
        correctly_linked_pairs=scores.correctly_linked_pairs,
        false_merge_pairs=scores.false_merge_pairs,
        gold_linked_pairs=scores.gold_linked_pairs,
        missed_link_pairs=scores.missed_link_pairs,
        duplicate_characters=scores.duplicate_characters,
        gold_multi_book_characters=scores.gold_multi_book_characters,
        **base,
    )


async def compare_graph_checksums(
    session: SQLModelAsyncSession, project_id: UUID, other_project_id: UUID
) -> bool:
    """True if two projects' character/relation sets hash identically.

    The Sprint 5 DoD's order-independence check: ingest a series forward
    into one project and reverse into another, then compare. Order does not
    matter to ``canonical_graph_checksum`` by construction (it sorts before
    hashing), so this is a straight equality check.
    """
    a = await compute_reconciliation_quality(session, project_id)
    b = await compute_reconciliation_quality(session, other_project_id)

    return a.graph_checksum is not None and a.graph_checksum == b.graph_checksum

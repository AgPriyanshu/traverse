"""Extraction-quality metrics against the S3.13 gold sets (S3.14).

Reads the already-frozen ``Character`` / ``CharacterAppearance`` /
``CharacterMention`` / ``RejectedCandidate`` tables the same way
``api/ops/pipeline_status.py`` already reads ``IngestionRun`` /
``IngestionStage`` -- nothing here writes to them, and nothing here belongs to
be1/be2's owned packages (``api/pipeline/**``, ``api/extraction/**``,
``api/graph/**``) even though it reads their tables.

The actual scoring logic lives in ``eval/metrics.py`` (repo-root ``eval/``, a
new do1-owned path this sprint) so it stays testable without Postgres; this
module is the DB-to-plain-data adapter plus the response shape for
``GET /ops/extraction-quality``. Informational only this sprint
(plans/sprint-3/devops-1.md S3.14) -- a regression gate lands in Sprint 8
(F6.4).
"""

from __future__ import annotations

import re
from contextlib import suppress
from uuid import UUID

from eval.loaders import CorpusChecksumMismatch, RosterSchemaError, load_gold_roster
from eval.metrics import (
    CharacterCluster,
    b3_precision_recall_f1,
    cascade_stage_contribution,
    match_rosters,
    rejection_precision,
    roster_precision_recall_f1,
    tier_accuracy,
)
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..db.models import (
    Book,
    Character,
    CharacterAppearance,
    CharacterMention,
    RejectedCandidate,
)


def _slugify_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _enum_value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


class ExtractionQualityOut(BaseModel):
    """``GET /ops/extraction-quality`` response.

    Locally defined here rather than in ``api/contracts/api.py`` -- that file
    is frozen as of the S3 freeze (BRANCH.md) and this response is consumed
    only by this sprint's ops dashboard, not by another agent's owned code.
    """

    book_id: UUID
    book_key: str | None = None
    gold_available: bool
    error: str | None = None

    roster_precision: float | None = None
    roster_recall: float | None = None
    roster_f1: float | None = None
    roster_true_positives: int | None = None
    roster_false_positives: int | None = None
    roster_false_negatives: int | None = None

    b3_precision: float | None = None
    b3_recall: float | None = None
    b3_f1: float | None = None
    b3_n_items: int | None = None

    tier_accuracy: float | None = None

    rejection_precision: float | None = None
    wrongly_rejected: list[str] = Field(default_factory=list)

    cascade_contribution: dict[str, int] = Field(default_factory=dict)
    cascade_fractions: dict[str, float] = Field(default_factory=dict)


async def compute_extraction_quality(
    session: SQLModelAsyncSession, book_id: UUID
) -> ExtractionQualityOut:
    """Score one book's current extraction output against its gold roster.

    Returns ``gold_available=False`` (not an error) for any book without a
    labelled gold set -- most books in the corpus don't have one
    (S3.13 covers only Pride and Prejudice and Wuthering Heights), and that
    is an expected, common case, not a failure.
    """
    book = await session.get(Book, book_id)
    if book is None:
        return ExtractionQualityOut(
            book_id=book_id, gold_available=False, error="book not found"
        )

    book_key = _slugify_title(book.title)
    try:
        gold = load_gold_roster(book_key)
    except FileNotFoundError:
        return ExtractionQualityOut(
            book_id=book_id, book_key=book_key, gold_available=False
        )
    except (RosterSchemaError, CorpusChecksumMismatch) as exc:
        return ExtractionQualityOut(
            book_id=book_id, book_key=book_key, gold_available=False, error=str(exc)
        )

    gold_clusters = [
        CharacterCluster(
            id=c["canonical_name"],
            canonical_name=c["canonical_name"],
            aliases=tuple(c["aliases"]),
            importance_tier=c["importance_tier"],
        )
        for c in gold["characters"]
    ]

    appearance_rows = (
        await session.execute(
            select(CharacterAppearance, Character)
            .join(Character, Character.id == CharacterAppearance.character_id)  # type: ignore[arg-type]
            .where(CharacterAppearance.book_id == book_id)  # type: ignore[arg-type]
        )
    ).all()

    predicted_clusters = [
        CharacterCluster(
            id=str(character.id),
            canonical_name=character.canonical_name,
            aliases=tuple(appearance.surface_forms),
            importance_tier=_enum_value(appearance.importance_tier),
        )
        for appearance, character in appearance_rows
    ]

    match = match_rosters(gold_clusters, predicted_clusters)
    roster_score = roster_precision_recall_f1(gold_clusters, predicted_clusters)
    tier_score = tier_accuracy(gold_clusters, predicted_clusters, match)

    # B3 at the alias/surface-form level: S3.13's gold data is a roster plus
    # an alias->canonical map, not per-occurrence mention tags, so "item" here
    # is a surface form, not a mention row (see eval/metrics.py's docstring).
    gold_item_clusters: dict[str, str] = {}
    for c in gold["characters"]:
        for alias in {c["canonical_name"], *c["aliases"]}:
            gold_item_clusters.setdefault(alias.strip().lower(), c["canonical_name"])

    predicted_item_clusters: dict[str, str] = {}
    for cluster in predicted_clusters:
        for form in cluster.surface_forms():
            predicted_item_clusters.setdefault(form, cluster.id)

    b3_result = None
    # No overlap yet (e.g. before be1's pass 1 has run) is not an error.
    with suppress(ValueError):
        b3_result = b3_precision_recall_f1(predicted_item_clusters, gold_item_clusters)

    rejected_rows = (
        (
            await session.execute(
                select(RejectedCandidate.surface_form).where(
                    RejectedCandidate.book_id == book_id  # type: ignore[arg-type]
                )
            )
        )
        .scalars()
        .all()
    )
    gold_character_forms = frozenset(
        form.strip().lower()
        for c in gold["characters"]
        for form in {c["canonical_name"], *c["aliases"]}
    )
    rejection_score = rejection_precision(list(rejected_rows), gold_character_forms)

    mention_methods = (
        (
            await session.execute(
                select(CharacterMention.resolution_method).where(
                    CharacterMention.book_id == book_id  # type: ignore[arg-type]
                )
            )
        )
        .scalars()
        .all()
    )
    cascade = cascade_stage_contribution([_enum_value(m) for m in mention_methods])

    return ExtractionQualityOut(
        book_id=book_id,
        book_key=book_key,
        gold_available=True,
        roster_precision=roster_score.precision,
        roster_recall=roster_score.recall,
        roster_f1=roster_score.f1,
        roster_true_positives=roster_score.true_positives,
        roster_false_positives=roster_score.false_positives,
        roster_false_negatives=roster_score.false_negatives,
        b3_precision=b3_result.precision if b3_result else None,
        b3_recall=b3_result.recall if b3_result else None,
        b3_f1=b3_result.f1 if b3_result else None,
        b3_n_items=b3_result.n_items if b3_result else None,
        tier_accuracy=tier_score,
        rejection_precision=rejection_score.precision,
        wrongly_rejected=list(rejection_score.wrongly_rejected),
        cascade_contribution=cascade.counts,
        cascade_fractions=cascade.fractions,
    )

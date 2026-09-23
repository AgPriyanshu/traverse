"""Relation-quality metrics against the S4.14 gold relations.

The database-to-plain-data adapter for ``eval/relation_metrics.py``, behind
``GET /ops/relation-quality``. Reads ``Relation``/``RelationEvidence`` and the
roster tables; writes nothing. Response models live here rather than in the
frozen ``api/contracts/api.py``, same as ``extraction_quality.py`` (SCR-2).
"""

from __future__ import annotations

import json
import re
from uuid import UUID

from eval.loaders import (
    GOLD_DIR,
    CorpusChecksumMismatch,
    RosterSchemaError,
    load_gold_relations,
    load_gold_roster,
)
from eval.metrics import CharacterCluster, match_rosters
from eval.relation_metrics import (
    DEFAULT_CHAPTER_TOLERANCE,
    PredictedEdge,
    citation_page_accuracy,
    gold_relations,
    ontology_view,
    score_relations,
)
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..db.models import (
    Book,
    Character,
    CharacterAppearance,
    Relation,
    RelationEvidence,
)


def _slugify_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


class PredicateScoreOut(BaseModel):
    predicate: str
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float | None
    recall: float | None
    f1: float | None


class RelationQualityOut(BaseModel):
    book_id: UUID
    book_key: str | None = None
    gold_available: bool
    error: str | None = None

    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    per_predicate: list[PredicateScoreOut] = Field(default_factory=list)
    spurious_edge_rate: float | None = None
    spurious_edges: list[str] = Field(default_factory=list)
    direction_accuracy: float | None = None
    direction_errors: list[str] = Field(default_factory=list)
    temporal_arc_accuracy: float | None = None
    temporal_transitions: int = 0
    temporal_correct: int = 0
    arcs_fully_correct: int = 0
    arcs_total: int = 0
    missed_gold: list[str] = Field(default_factory=list)
    scored_edges: int = 0
    unmapped_edges: int = 0

    evidence_free_edges: int | None = None
    evidence_free_edges_graph: int | None = None
    evidence_invariant_holds: bool | None = None

    citation_judged: int = 0
    citation_accuracy: float | None = None
    citation_meets_target: bool = False


async def count_evidence_free_edges(
    session: SQLModelAsyncSession, project_id: UUID
) -> int:
    """Relations in ``project_id`` with no evidence row. Must always be 0."""
    statement = (
        select(func.count(Relation.id))  # type: ignore[arg-type]
        .outerjoin(RelationEvidence, RelationEvidence.relation_id == Relation.id)  # type: ignore[arg-type]
        .where(
            Relation.project_id == project_id,  # type: ignore[arg-type]
            RelationEvidence.id.is_(None),  # type: ignore[union-attr]
        )
    )
    count = (await session.execute(statement)).scalar_one()

    return int(count)


async def count_evidence_free_graph_edges() -> int | None:
    """``RELATED`` edges in Neo4j with no evidence, or ``None`` if unreachable."""
    from ..graph import client

    query = (
        "MATCH ()-[r:RELATED]->() "
        "WHERE coalesce(r.evidence_count, 0) = 0 "
        "OR size(coalesce(r.page_refs, [])) = 0 RETURN count(r) AS n"
    )
    try:
        result = await client.execute(query)
    except Exception:
        return None
    records = result.records

    return int(records[0]["n"]) if records else 0


def judgements_path(book_key: str):
    return GOLD_DIR / book_key.replace("-", "_") / "citation_judgements.json"


def _load_judgements(book_key: str) -> list[dict]:
    path = judgements_path(book_key)
    if not path.exists():
        return []

    return json.loads(path.read_text()).get("judgements", [])


async def compute_relation_quality(
    session: SQLModelAsyncSession, book_id: UUID
) -> RelationQualityOut:
    """Score one book's relations against its gold relations.

    Returns ``gold_available=False`` (not an error) for a book without labelled
    relations. The evidence-free counts are still reported in that case: the
    zero-evidence invariant does not need gold.
    """
    book = await session.get(Book, book_id)
    if book is None:
        return RelationQualityOut(
            book_id=book_id, gold_available=False, error="book not found"
        )

    evidence_free = await count_evidence_free_edges(session, book.project_id)
    evidence_free_graph = await count_evidence_free_graph_edges()
    invariant = evidence_free == 0 and evidence_free_graph in (0, None)
    base = {
        "evidence_free_edges": evidence_free,
        "evidence_free_edges_graph": evidence_free_graph,
        "evidence_invariant_holds": invariant,
    }

    book_key = _slugify_title(book.title)
    try:
        document = load_gold_relations(book_key)
        roster = load_gold_roster(book_key)
    except FileNotFoundError:
        return RelationQualityOut(
            book_id=book_id, book_key=book_key, gold_available=False, **base
        )
    except (RosterSchemaError, CorpusChecksumMismatch) as exc:
        return RelationQualityOut(
            book_id=book_id,
            book_key=book_key,
            gold_available=False,
            error=str(exc),
            **base,
        )

    in_scope = set(document["scope_tiers"])
    gold_clusters = [
        CharacterCluster(
            id=c["canonical_name"],
            canonical_name=c["canonical_name"],
            aliases=tuple(c["aliases"]),
            importance_tier=c["importance_tier"],
        )
        for c in roster["characters"]
        if c["importance_tier"] in in_scope
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
        )
        for appearance, character in appearance_rows
    ]
    match = match_rosters(gold_clusters, predicted_clusters)
    to_gold = {m.predicted_id: m.gold_id for m in match.matches}

    relation_rows = (
        (
            await session.execute(
                select(Relation)
                .join(RelationEvidence, RelationEvidence.relation_id == Relation.id)  # type: ignore[arg-type]
                .where(RelationEvidence.book_id == book_id)  # type: ignore[arg-type]
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    edges: list[PredictedEdge] = []
    unmapped = 0
    for relation in relation_rows:
        subject = to_gold.get(str(relation.subject_character_id))
        obj = to_gold.get(str(relation.object_character_id))
        if subject is None or obj is None:
            unmapped += 1
            continue
        edges.append(
            PredictedEdge(
                subject=subject,
                predicate=relation.predicate,
                object=obj,
                first_chapter=relation.first_chapter,
                last_chapter=relation.last_chapter,
                evidence_count=relation.evidence_count,
            )
        )

    scores = score_relations(
        gold_relations(document),
        edges,
        ontology_view(),
        ignored_predicates=document.get("ignored_predicates", []),
        chapter_tolerance=document.get("chapter_tolerance", DEFAULT_CHAPTER_TOLERANCE),
    )
    citation = citation_page_accuracy(_load_judgements(book_key))

    def label(edge: PredictedEdge) -> str:
        return f"{edge.subject} {edge.predicate} {edge.object}"

    return RelationQualityOut(
        book_id=book_id,
        book_key=book_key,
        gold_available=True,
        precision=scores.overall.precision,
        recall=scores.overall.recall,
        f1=scores.overall.f1,
        per_predicate=[
            PredicateScoreOut(
                predicate=s.predicate,
                true_positives=s.tp,
                false_positives=s.fp,
                false_negatives=s.fn,
                precision=s.prf.precision,
                recall=s.prf.recall,
                f1=s.prf.f1,
            )
            for s in scores.per_predicate
        ],
        spurious_edge_rate=scores.spurious_edge_rate,
        spurious_edges=[label(e) for e in scores.spurious_edges],
        direction_accuracy=scores.direction_accuracy,
        direction_errors=[label(e) for e in scores.direction_errors],
        temporal_arc_accuracy=scores.temporal_arc_accuracy,
        temporal_transitions=scores.temporal_transitions,
        temporal_correct=scores.temporal_correct,
        arcs_fully_correct=scores.arcs_fully_correct,
        arcs_total=scores.arcs_total,
        missed_gold=[f"{g.subject} {g.predicate} {g.object}" for g in scores.missed],
        scored_edges=scores.predicted_scored,
        unmapped_edges=unmapped,
        citation_judged=citation.judged,
        citation_accuracy=citation.accuracy,
        citation_meets_target=citation.meets_target,
        **base,
    )

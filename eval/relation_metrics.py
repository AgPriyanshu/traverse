"""Relation-quality metrics against the S4.14 gold relations.

Pure functions over plain data, so they are testable without Postgres or Neo4j.
``api/ops/relation_quality.py`` adapts the real ``Relation`` rows into
``PredictedEdge`` values, mapping each database character onto a gold roster
character first; everything here speaks gold canonical names.

Matching is done after inverse normalisation: ``child_of(a, b)`` and
``parent_of(b, a)`` are one fact, and a symmetric predicate ignores order. A
reversed asymmetric edge is not the same fact, and is reported separately as a
direction error rather than folded into an F1.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .metrics import PrecisionRecallF1, precision_recall_f1

CITATION_TARGET = 0.95
CITATION_MIN_SAMPLE = 50
DEFAULT_CHAPTER_TOLERANCE = 3


@dataclass(frozen=True)
class OntologyView:
    inverse: dict[str, str | None]
    symmetric: frozenset[str]

    def class_name(self, predicate: str) -> str:
        """One name for a predicate and its inverse, so both report together."""
        inverse = self.inverse.get(predicate)

        return min(predicate, inverse) if inverse else predicate

    def canonical(self, subject: str, predicate: str, obj: str) -> tuple[str, str, str]:
        """The one tuple a fact is compared by, whichever way it was written."""
        if predicate in self.symmetric:
            first, second = sorted((subject, obj))

            return (predicate, first, second)
        forms = [(predicate, subject, obj)]
        inverse = self.inverse.get(predicate)
        if inverse:
            forms.append((inverse, obj, subject))

        return min(forms)


def ontology_view() -> OntologyView:
    """Build the view from ``api/graph/ontology.yaml`` (the single source)."""
    from api.graph.ontology import ONTOLOGY

    specs = ONTOLOGY.predicates.values()
    inverse = {spec.name: spec.inverse for spec in specs}
    symmetric = frozenset(spec.name for spec in specs if spec.symmetric)

    return OntologyView(inverse=inverse, symmetric=symmetric)


@dataclass(frozen=True)
class PredictedEdge:
    subject: str
    predicate: str
    object: str
    first_chapter: int | None = None
    last_chapter: int | None = None
    evidence_count: int = 0


@dataclass(frozen=True)
class GoldRelation:
    subject: str
    predicate: str
    object: str
    chapters: tuple[int, int]
    alt_predicates: tuple[str, ...] = ()
    arc: str | None = None

    def acceptable(self) -> tuple[str, ...]:
        return (self.predicate, *self.alt_predicates)


def gold_relations(document: dict[str, Any]) -> list[GoldRelation]:
    """Flatten a schema-valid gold relations document."""
    return [
        GoldRelation(
            subject=item["subject"],
            predicate=item["predicate"],
            object=item["object"],
            chapters=(item["chapters"][0], item["chapters"][1]),
            alt_predicates=tuple(item.get("alt_predicates", [])),
            arc=item.get("arc"),
        )
        for item in document["relations"]
    ]


def _pair(subject: str, obj: str) -> frozenset[str]:
    return frozenset((subject, obj))


@dataclass
class PredicateScore:
    predicate: str
    tp: int
    fp: int
    fn: int
    prf: PrecisionRecallF1


@dataclass
class RelationScores:
    per_predicate: list[PredicateScore]
    overall: PrecisionRecallF1
    spurious_edge_rate: float | None
    spurious_edges: list[PredictedEdge]
    direction_accuracy: float | None
    direction_errors: list[PredictedEdge]
    temporal_arc_accuracy: float | None
    temporal_transitions: int
    temporal_correct: int
    arcs_fully_correct: int
    arcs_total: int
    predicted_scored: int
    missed: list[GoldRelation] = field(default_factory=list)


def score_relations(
    gold: Iterable[GoldRelation],
    predicted: Iterable[PredictedEdge],
    view: OntologyView,
    *,
    ignored_predicates: Iterable[str] = (),
    chapter_tolerance: int = DEFAULT_CHAPTER_TOLERANCE,
) -> RelationScores:
    """Score predicted edges against closed-world gold relations.

    Args:
        gold: Gold relations between in-scope characters.
        predicted: Predicted edges already restricted to in-scope characters
            and mapped onto gold canonical names.
        view: Inverse and symmetry data from the ontology.
        ignored_predicates: Predicates dropped from ``predicted`` before
            scoring, because gold does not assert their absence.
        chapter_tolerance: Allowed chapter distance for a transition.

    Returns:
        Per-predicate and overall precision/recall/F1, spurious edge rate,
        direction accuracy and temporal arc accuracy.
    """
    gold_list = list(gold)
    ignored = set(ignored_predicates)
    edges = [e for e in predicted if e.predicate not in ignored]

    gold_keys: list[set[tuple[str, str, str]]] = [
        {view.canonical(g.subject, q, g.object) for q in g.acceptable()}
        for g in gold_list
    ]
    all_gold_keys = set().union(*gold_keys) if gold_keys else set()
    gold_pairs = {_pair(g.subject, g.object) for g in gold_list}
    gold_classes: dict[frozenset[str], set[str]] = defaultdict(set)
    for g in gold_list:
        for q in g.acceptable():
            gold_classes[_pair(g.subject, g.object)].add(view.class_name(q))

    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)
    matched_gold: set[int] = set()

    for edge in edges:
        key = view.canonical(edge.subject, edge.predicate, edge.object)
        hits = [i for i, keys in enumerate(gold_keys) if key in keys]
        if hits:
            matched_gold.update(hits)
        else:
            fp[view.class_name(edge.predicate)] += 1

    for i, g in enumerate(gold_list):
        name = view.class_name(g.predicate)
        if i in matched_gold:
            tp[name] += 1
        else:
            fn[name] += 1

    names = sorted(set(tp) | set(fp) | set(fn))
    per_predicate = [
        PredicateScore(n, tp[n], fp[n], fn[n], precision_recall_f1(tp[n], fp[n], fn[n]))
        for n in names
    ]
    overall = precision_recall_f1(sum(tp.values()), sum(fp.values()), sum(fn.values()))

    spurious = [e for e in edges if _pair(e.subject, e.object) not in gold_pairs]
    spurious_rate = len(spurious) / len(edges) if edges else None

    attempts = 0
    direction_correct = 0
    direction_errors: list[PredictedEdge] = []
    for edge in edges:
        pair = _pair(edge.subject, edge.object)
        if view.class_name(edge.predicate) not in gold_classes.get(pair, set()):
            continue
        attempts += 1
        key = view.canonical(edge.subject, edge.predicate, edge.object)
        if key in all_gold_keys:
            direction_correct += 1
        else:
            direction_errors.append(edge)
    direction_accuracy = direction_correct / attempts if attempts else None

    transitions, transitions_correct, arcs_ok, arcs_total = _score_arcs(
        gold_list, gold_keys, edges, view, chapter_tolerance
    )

    return RelationScores(
        per_predicate=per_predicate,
        overall=overall,
        spurious_edge_rate=spurious_rate,
        spurious_edges=spurious,
        direction_accuracy=direction_accuracy,
        direction_errors=direction_errors,
        temporal_arc_accuracy=(
            transitions_correct / transitions if transitions else None
        ),
        temporal_transitions=transitions,
        temporal_correct=transitions_correct,
        arcs_fully_correct=arcs_ok,
        arcs_total=arcs_total,
        predicted_scored=len(edges),
        missed=[g for i, g in enumerate(gold_list) if i not in matched_gold],
    )


def _score_arcs(
    gold_list: list[GoldRelation],
    gold_keys: list[set[tuple[str, str, str]]],
    edges: list[PredictedEdge],
    view: OntologyView,
    tolerance: int,
) -> tuple[int, int, int, int]:
    arcs: dict[tuple[frozenset[str], str], list[int]] = defaultdict(list)
    for i, g in enumerate(gold_list):
        if g.arc:
            arcs[(_pair(g.subject, g.object), g.arc)].append(i)

    transitions = 0
    correct = 0
    arcs_ok = 0
    for indices in arcs.values():
        ordered = sorted(indices, key=lambda i: gold_list[i].chapters[0])
        arc_correct = True
        for i in ordered[1:]:
            transitions += 1
            target = gold_list[i].chapters[0]
            hit = any(
                view.canonical(e.subject, e.predicate, e.object) in gold_keys[i]
                and e.first_chapter is not None
                and abs(e.first_chapter - target) <= tolerance
                for e in edges
            )
            if hit:
                correct += 1
            else:
                arc_correct = False
        if arc_correct:
            arcs_ok += 1

    return transitions, correct, arcs_ok, len(arcs)


@dataclass(frozen=True)
class CitationScore:
    judged: int
    supported: int
    accuracy: float | None
    meets_target: bool
    sample_large_enough: bool


def citation_page_accuracy(judgements: Iterable[dict[str, Any]]) -> CitationScore:
    """Share of human-judged citations whose cited page supports the claim.

    Args:
        judgements: Dicts with a boolean ``supported`` key, as written by
            ``scripts/judge_citations.py``. Skipped items carry ``None`` and are
            not counted.

    Returns:
        The accuracy and whether it clears F3.2's 95% on a sample of at least 50.
    """
    verdicts = [j["supported"] for j in judgements if j.get("supported") is not None]
    judged = len(verdicts)
    supported = sum(1 for v in verdicts if v)
    accuracy = supported / judged if judged else None
    large_enough = judged >= CITATION_MIN_SAMPLE

    return CitationScore(
        judged=judged,
        supported=supported,
        accuracy=accuracy,
        meets_target=accuracy is not None
        and accuracy >= CITATION_TARGET
        and large_enough,
        sample_large_enough=large_enough,
    )

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

ACCURACY_TARGET = 0.85
CITATION_PRECISION_TARGET = 0.95
ABSTENTION_TARGET = 0.90


@dataclass(frozen=True)
class GoldQuestion:
    id: str
    question: str
    qclass: str
    expect_abstain: bool
    expected_answer: str | None = None
    expected_entities: tuple[str, ...] = ()
    min_citations: int = 1


def gold_questions(document: dict[str, Any]) -> list[GoldQuestion]:
    """Flatten a schema-valid gold answers document."""
    return [
        GoldQuestion(
            id=item["id"],
            question=item["question"],
            qclass=item["class"],
            expect_abstain=item["expect_abstain"],
            expected_answer=item.get("expected_answer"),
            expected_entities=tuple(item.get("expected_entities", [])),
            min_citations=item.get("min_citations", 1),
        )
        for item in document["questions"]
    ]


@dataclass(frozen=True)
class AnsweredCitation:
    book_id: str
    page_start: int
    page_end: int
    quote: str | None = None


@dataclass(frozen=True)
class AnsweredQuery:
    """One question's real answer, as logged by the query pipeline."""

    question_id: str
    answer: str | None
    abstained: bool
    citations: tuple[AnsweredCitation, ...] = ()
    predicted_entities: tuple[str, ...] = ()


@dataclass(frozen=True)
class JudgeVerdict:
    """One LLM-judge verdict for a question (``api/ops/answer_judge.py``).

    ``correct`` and each entry of ``citation_supported`` are ``None`` when the
    judge was never run for that item (no answer to judge yet, or the judge
    call itself failed) -- kept out of every average rather than counted
    against it.
    """

    question_id: str
    correct: bool | None
    citation_supported: tuple[bool | None, ...] = ()
    reasoning: str | None = None


@dataclass(frozen=True)
class RateWithSample:
    hit: int
    total: int
    rate: float | None
    meets_target: bool
    target: float


def _rate(hit: int, total: int, target: float) -> RateWithSample:
    rate = hit / total if total else None

    return RateWithSample(
        hit=hit,
        total=total,
        rate=rate,
        meets_target=rate is not None and rate >= target,
        target=target,
    )


@dataclass
class ClassScore:
    qclass: str
    judged: int
    correct: int
    accuracy: float | None


@dataclass
class AggregationMiss:
    question_id: str
    expected: tuple[str, ...]
    predicted: tuple[str, ...]
    missing: tuple[str, ...]
    extra: tuple[str, ...]


@dataclass
class AnswerScores:
    accuracy: RateWithSample
    per_class: list[ClassScore]
    citation_precision: RateWithSample
    abstention: RateWithSample
    aggregation_exact_match: RateWithSample
    aggregation_misses: list[AggregationMiss] = field(default_factory=list)
    answered: int = 0
    unanswered: int = 0
    total_gold: int = 0


def score_answers(
    gold: Iterable[GoldQuestion],
    answered: Iterable[AnsweredQuery],
    verdicts: Iterable[JudgeVerdict],
) -> AnswerScores:
    """Score a run's answered, judged questions against the gold set.

    Args:
        gold: The question set a run was meant to cover.
        answered: What the query pipeline actually returned, one row per
            question that was asked (a question never asked is absent here,
            not present with a null answer).
        verdicts: The judge's verdicts, keyed the same way.

    Returns:
        Accuracy (overall and per class), citation precision, abstention
        rate, and aggregation exact-set-match rate.
    """
    gold_by_id = {g.id: g for g in gold}
    answered_by_id = {a.question_id: a for a in answered}
    verdict_by_id = {v.question_id: v for v in verdicts}

    total_gold = len(gold_by_id)
    answered_ids = set(answered_by_id) & set(gold_by_id)
    unanswered = total_gold - len(answered_ids)

    accuracy_hit = 0
    accuracy_total = 0
    per_class_hit: dict[str, int] = defaultdict(int)
    per_class_total: dict[str, int] = defaultdict(int)

    citation_hit = 0
    citation_total = 0

    abstain_hit = 0
    abstain_total = 0

    agg_hit = 0
    agg_total = 0
    agg_misses: list[AggregationMiss] = []

    for question_id in answered_ids:
        g = gold_by_id[question_id]
        a = answered_by_id[question_id]
        v = verdict_by_id.get(question_id)

        if g.expect_abstain:
            abstain_total += 1
            if a.abstained:
                abstain_hit += 1
        elif not a.abstained and v is not None and v.correct is not None:
            # Only a real, judged, non-abstained answer counts toward
            # accuracy -- a question the system wrongly abstained on is
            # scored against abstention, not silently dropped from accuracy.
            accuracy_total += 1
            per_class_total[g.qclass] += 1
            if v.correct:
                accuracy_hit += 1
                per_class_hit[g.qclass] += 1

        if v is not None:
            for supported in v.citation_supported:
                if supported is None:
                    continue
                citation_total += 1
                if supported:
                    citation_hit += 1

        if g.qclass == "aggregation" and g.expected_entities and not a.abstained:
            agg_total += 1
            expected = set(g.expected_entities)
            predicted = set(a.predicted_entities)
            if expected == predicted:
                agg_hit += 1
            else:
                agg_misses.append(
                    AggregationMiss(
                        question_id=question_id,
                        expected=tuple(sorted(expected)),
                        predicted=tuple(sorted(predicted)),
                        missing=tuple(sorted(expected - predicted)),
                        extra=tuple(sorted(predicted - expected)),
                    )
                )

    per_class = sorted(
        (
            ClassScore(
                qclass=qclass,
                judged=per_class_total[qclass],
                correct=per_class_hit[qclass],
                accuracy=(
                    per_class_hit[qclass] / per_class_total[qclass]
                    if per_class_total[qclass]
                    else None
                ),
            )
            for qclass in per_class_total
        ),
        key=lambda c: c.qclass,
    )

    return AnswerScores(
        accuracy=_rate(accuracy_hit, accuracy_total, ACCURACY_TARGET),
        per_class=per_class,
        citation_precision=_rate(citation_hit, citation_total, CITATION_PRECISION_TARGET),
        abstention=_rate(abstain_hit, abstain_total, ABSTENTION_TARGET),
        aggregation_exact_match=_rate(agg_hit, agg_total, 1.0),
        aggregation_misses=agg_misses,
        answered=len(answered_ids),
        unanswered=unanswered,
        total_gold=total_gold,
    )

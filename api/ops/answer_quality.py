from __future__ import annotations

import json
from pathlib import Path

from eval.answer_metrics import (
    AnsweredCitation,
    AnsweredQuery,
    JudgeVerdict,
    gold_questions,
    score_answers,
)
from eval.loaders import (
    GOLD_DIR,
    CorpusChecksumMismatch,
    RosterSchemaError,
    load_gold_answers,
)
from pydantic import BaseModel, Field


def judgements_path(book_key: str) -> Path:
    return GOLD_DIR / book_key.replace("-", "_") / "answer_judgements.json"


def _load_judgements(book_key: str) -> list[dict]:
    path = judgements_path(book_key)
    if not path.exists():
        return []

    return json.loads(path.read_text()).get("answers", [])


class RateOut(BaseModel):
    hit: int
    total: int
    rate: float | None
    meets_target: bool
    target: float


class ClassScoreOut(BaseModel):
    qclass: str
    judged: int
    correct: int
    accuracy: float | None


class AggregationMissOut(BaseModel):
    question_id: str
    expected: list[str]
    predicted: list[str]
    missing: list[str]
    extra: list[str]


class AnswerQualityOut(BaseModel):
    book_key: str
    gold_available: bool
    error: str | None = None

    total_gold: int = 0
    answered: int = 0
    unanswered: int = 0

    accuracy: RateOut | None = None
    per_class: list[ClassScoreOut] = Field(default_factory=list)
    citation_precision: RateOut | None = None
    abstention: RateOut | None = None
    aggregation_exact_match: RateOut | None = None
    aggregation_misses: list[AggregationMissOut] = Field(default_factory=list)


def _rate_out(rate) -> RateOut:
    return RateOut(
        hit=rate.hit,
        total=rate.total,
        rate=rate.rate,
        meets_target=rate.meets_target,
        target=rate.target,
    )


def _row_to_answered(row: dict) -> AnsweredQuery:
    citations = tuple(
        AnsweredCitation(
            book_id=str(c.get("book_id", "")),
            page_start=c["page_start"],
            page_end=c.get("page_end", c["page_start"]),
            quote=c.get("quote"),
        )
        for c in row.get("citations", [])
    )

    return AnsweredQuery(
        question_id=row["question_id"],
        answer=row.get("answer"),
        abstained=bool(row.get("abstained", False)),
        citations=citations,
        predicted_entities=tuple(row.get("predicted_entities", [])),
    )


def _row_to_verdict(row: dict) -> JudgeVerdict | None:
    judge = row.get("judge")
    if judge is None:
        return None

    return JudgeVerdict(
        question_id=row["question_id"],
        correct=judge.get("correct"),
        citation_supported=tuple(judge.get("citation_supported", [])),
        reasoning=judge.get("reasoning"),
    )


def compute_answer_quality(book_key: str) -> AnswerQualityOut:
    """Score one book's judged answer run against its gold question set.

    Returns ``gold_available=False`` (not an error) for a book without a
    labelled question set, and a zeroed, ``gold_available=True`` report for
    one with no judged run yet.
    """
    try:
        document = load_gold_answers(book_key)
    except FileNotFoundError:
        return AnswerQualityOut(book_key=book_key, gold_available=False)
    except (RosterSchemaError, CorpusChecksumMismatch) as exc:
        return AnswerQualityOut(book_key=book_key, gold_available=False, error=str(exc))

    gold = gold_questions(document)
    rows = _load_judgements(book_key)
    answered = [_row_to_answered(r) for r in rows]
    verdicts = [v for r in rows if (v := _row_to_verdict(r)) is not None]

    scores = score_answers(gold, answered, verdicts)

    return AnswerQualityOut(
        book_key=book_key,
        gold_available=True,
        total_gold=scores.total_gold,
        answered=scores.answered,
        unanswered=scores.unanswered,
        accuracy=_rate_out(scores.accuracy),
        per_class=[
            ClassScoreOut(
                qclass=c.qclass, judged=c.judged, correct=c.correct, accuracy=c.accuracy
            )
            for c in scores.per_class
        ],
        citation_precision=_rate_out(scores.citation_precision),
        abstention=_rate_out(scores.abstention),
        aggregation_exact_match=_rate_out(scores.aggregation_exact_match),
        aggregation_misses=[
            AggregationMissOut(
                question_id=m.question_id,
                expected=list(m.expected),
                predicted=list(m.predicted),
                missing=list(m.missing),
                extra=list(m.extra),
            )
            for m in scores.aggregation_misses
        ],
    )

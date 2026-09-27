from eval.answer_metrics import (
    AnsweredCitation,
    AnsweredQuery,
    GoldQuestion,
    JudgeVerdict,
    gold_questions,
    score_answers,
)


def _gold(**overrides):
    base = dict(
        id="q1",
        question="Who is X?",
        qclass="single_fact",
        expect_abstain=False,
        expected_answer="X is X.",
    )
    base.update(overrides)

    return GoldQuestion(**base)


def test_correct_judged_answer_counts_toward_accuracy():
    gold = [_gold()]
    answered = [AnsweredQuery(question_id="q1", answer="X is X.", abstained=False)]
    verdicts = [JudgeVerdict(question_id="q1", correct=True)]
    scores = score_answers(gold, answered, verdicts)

    assert scores.accuracy.hit == 1
    assert scores.accuracy.total == 1
    assert scores.accuracy.rate == 1.0
    assert scores.answered == 1
    assert scores.unanswered == 0


def test_unjudged_answer_does_not_count_either_way():
    gold = [_gold()]
    answered = [AnsweredQuery(question_id="q1", answer="X is X.", abstained=False)]
    scores = score_answers(gold, answered, verdicts=[])

    assert scores.accuracy.total == 0
    assert scores.accuracy.rate is None


def test_a_question_never_asked_is_unanswered_not_wrong():
    gold = [_gold(id="q1"), _gold(id="q2")]
    answered = [AnsweredQuery(question_id="q1", answer="X is X.", abstained=False)]
    verdicts = [JudgeVerdict(question_id="q1", correct=True)]
    scores = score_answers(gold, answered, verdicts)

    assert scores.total_gold == 2
    assert scores.answered == 1
    assert scores.unanswered == 1


def test_abstention_on_an_unanswerable_question_is_a_hit():
    gold = [_gold(id="q1", expect_abstain=True, expected_answer=None)]
    answered = [AnsweredQuery(question_id="q1", answer=None, abstained=True)]
    scores = score_answers(gold, answered, verdicts=[])

    assert scores.abstention.hit == 1
    assert scores.abstention.total == 1
    assert scores.abstention.rate == 1.0
    # Abstention questions never enter the accuracy pool.
    assert scores.accuracy.total == 0


def test_confident_wrong_answer_on_an_unanswerable_question_misses_abstention():
    gold = [_gold(id="q1", expect_abstain=True, expected_answer=None)]
    answered = [
        AnsweredQuery(question_id="q1", answer="She has a brother.", abstained=False)
    ]
    # Even a judge marking this "correct" must never rescue an abstention miss.
    verdicts = [JudgeVerdict(question_id="q1", correct=True)]
    scores = score_answers(gold, answered, verdicts)

    assert scores.abstention.hit == 0
    assert scores.abstention.total == 1
    assert scores.abstention.rate == 0.0


def test_citation_precision_averages_over_every_judged_citation_across_questions():
    gold = [_gold(id="q1"), _gold(id="q2")]
    answered = [
        AnsweredQuery(
            question_id="q1",
            answer="a",
            abstained=False,
            citations=(AnsweredCitation(book_id="b", page_start=1, page_end=1),),
        ),
        AnsweredQuery(
            question_id="q2",
            answer="b",
            abstained=False,
            citations=(
                AnsweredCitation(book_id="b", page_start=2, page_end=2),
                AnsweredCitation(book_id="b", page_start=3, page_end=3),
            ),
        ),
    ]
    verdicts = [
        JudgeVerdict(question_id="q1", correct=True, citation_supported=(True,)),
        JudgeVerdict(
            question_id="q2", correct=True, citation_supported=(True, False)
        ),
    ]
    scores = score_answers(gold, answered, verdicts)

    assert scores.citation_precision.hit == 2
    assert scores.citation_precision.total == 3
    assert round(scores.citation_precision.rate, 3) == round(2 / 3, 3)


def test_aggregation_exact_set_match_rejects_a_plausible_subset():
    gold = [
        _gold(
            id="q1",
            qclass="aggregation",
            expected_entities=("Jane", "Elizabeth", "Mary", "Kitty", "Lydia"),
        )
    ]
    # Four of the five daughters -- exactly the F4.1 failure mode this metric
    # exists to catch.
    answered = [
        AnsweredQuery(
            question_id="q1",
            answer="Jane, Elizabeth, Mary and Kitty.",
            abstained=False,
            predicted_entities=("Jane", "Elizabeth", "Mary", "Kitty"),
        )
    ]
    scores = score_answers(gold, answered, verdicts=[])

    assert scores.aggregation_exact_match.hit == 0
    assert scores.aggregation_exact_match.total == 1
    assert len(scores.aggregation_misses) == 1
    assert scores.aggregation_misses[0].missing == ("Lydia",)
    assert scores.aggregation_misses[0].extra == ()


def test_aggregation_exact_set_match_accepts_the_full_set():
    gold = [
        _gold(
            id="q1",
            qclass="aggregation",
            expected_entities=("Jane", "Elizabeth"),
        )
    ]
    answered = [
        AnsweredQuery(
            question_id="q1",
            answer="Jane and Elizabeth.",
            abstained=False,
            predicted_entities=("Elizabeth", "Jane"),
        )
    ]
    scores = score_answers(gold, answered, verdicts=[])

    assert scores.aggregation_exact_match.hit == 1
    assert scores.aggregation_misses == []


def test_gold_questions_flattens_a_schema_valid_document():
    document = {
        "questions": [
            {
                "id": "pp-001",
                "question": "Who is Mr Collins?",
                "class": "single_fact",
                "expect_abstain": False,
                "expected_answer": "William Collins.",
            },
            {
                "id": "pp-002",
                "question": "Who are Mr Bennet's daughters?",
                "class": "aggregation",
                "expect_abstain": False,
                "expected_entities": ["Jane", "Elizabeth"],
                "min_citations": 2,
            },
        ]
    }
    parsed = gold_questions(document)

    assert len(parsed) == 2
    assert parsed[0].qclass == "single_fact"
    assert parsed[1].expected_entities == ("Jane", "Elizabeth")
    assert parsed[1].min_citations == 2

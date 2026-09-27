import pytest

from api.contracts.enums import QueryRoute
from api.query import router
from api.query.eval_router import RoutingExample, evaluate, load_examples


@pytest.mark.asyncio
async def test_classify_question_returns_the_stubbed_structured_output(monkeypatch):
    async def fake_structured_call(_prompt, schema, **_kwargs):
        return schema(
            route=QueryRoute.RELATIONSHIP_LOOKUP,
            subject_phrase="Elizabeth",
            object_phrase="Mr Darcy",
            predicate_hint=None,
        )

    monkeypatch.setattr(router, "structured_call", fake_structured_call)

    result = await router.classify_question(
        "How does Elizabeth know Mr Darcy?", project_id="p1"
    )

    assert result.route is QueryRoute.RELATIONSHIP_LOOKUP
    assert result.subject_phrase == "Elizabeth"
    assert result.object_phrase == "Mr Darcy"


def test_routing_question_fixture_covers_every_class():
    from pathlib import Path

    examples = load_examples(Path("api/tests/fixtures/query/routing_questions.jsonl"))
    classes = {example.expected_route for example in examples}

    assert classes == set(QueryRoute)
    assert len(examples) >= 60


@pytest.mark.asyncio
async def test_evaluate_builds_a_confusion_matrix_from_stubbed_calls(monkeypatch):
    """Exercises the eval harness mechanics against a deterministic stub.

    The real accuracy number against the live model is measured separately
    (``api/query/eval_router.py``'s module docstring) — this only proves the
    harness counts hits, misses, and errors correctly.
    """
    examples = [
        RoutingExample("q1", QueryRoute.CHARACTER_LOOKUP),
        RoutingExample("q2", QueryRoute.CHARACTER_LOOKUP),
        RoutingExample("q3", QueryRoute.AGGREGATION),
        RoutingExample("q4", QueryRoute.NARRATIVE),
    ]

    async def fake_classify(question, *, project_id):
        del project_id
        # q1 correct, q2 misrouted as narrative, q3 correct, q4 raises.
        mapping = {
            "q1": QueryRoute.CHARACTER_LOOKUP,
            "q2": QueryRoute.NARRATIVE,
            "q3": QueryRoute.AGGREGATION,
        }
        if question not in mapping:
            raise RuntimeError("simulated call failure")

        return type("R", (), {"route": mapping[question]})()

    import api.query.eval_router as eval_router_module

    monkeypatch.setattr(eval_router_module, "classify_question", fake_classify)

    result = await evaluate(examples, project_id="p1")

    assert result.total == 4
    assert len(result.errors) == 1
    assert result.confusion[("character_lookup", "character_lookup")] == 1
    assert result.confusion[("character_lookup", "narrative")] == 1
    assert result.confusion[("aggregation", "aggregation")] == 1
    # 2 correct out of 4 total (the error counts against accuracy, not against total).
    assert result.accuracy == pytest.approx(0.5)

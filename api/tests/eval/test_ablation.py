import pytest

from api.contracts.api import AblationConfig
from api.contracts.enums import InferenceMode
from api.eval.ablation import AblationAxisNotOwned, ResolvedAblation, resolve
from api.retrieval import RetrievalMode


@pytest.mark.parametrize(
    "retrieval_mode,expected",
    [
        ("vector_only", RetrievalMode.VECTOR_ONLY),
        ("bm25", RetrievalMode.BM25),
        ("rerank", RetrievalMode.RERANK),
        ("graph_constrained", RetrievalMode.GRAPH_CONSTRAINED),
    ],
)
def test_resolves_every_declared_retrieval_mode(retrieval_mode, expected):
    config = AblationConfig(
        axis="retrieval", label=retrieval_mode, retrieval_mode=retrieval_mode
    )

    resolved = resolve(config)

    assert resolved == ResolvedAblation(retrieval_mode=expected, inference_mode=None)


@pytest.mark.parametrize(
    "model_mode,expected",
    [
        ("local", InferenceMode.LOCAL),
        ("frontier", InferenceMode.API),
        ("routed", InferenceMode.ROUTED),
    ],
)
def test_resolves_every_declared_model_mode(model_mode, expected):
    config = AblationConfig(axis="model", label=model_mode, model_mode=model_mode)

    resolved = resolve(config)

    assert resolved == ResolvedAblation(retrieval_mode=None, inference_mode=expected)


def test_extraction_axis_is_refused_not_silently_ignored():
    config = AblationConfig(axis="extraction", label="two_pass_full_cascade")

    with pytest.raises(AblationAxisNotOwned, match="extraction"):
        resolve(config)


def test_retrieval_axis_without_a_mode_resolves_to_recommended_default():
    """A cell can name an axis for bookkeeping without overriding a mode --
    the resolved value must stay ``None`` (today's default), not error."""
    config = AblationConfig(axis="retrieval", label="recommended")

    resolved = resolve(config)

    assert resolved == ResolvedAblation(retrieval_mode=None, inference_mode=None)

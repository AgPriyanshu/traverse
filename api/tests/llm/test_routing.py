import pytest

from api.config.settings import settings
from api.contracts.enums import InferenceMode, LLMPurpose
from api.llm.errors import PermanentLLMError
from api.llm.routing import route_for


@pytest.mark.parametrize(
    "purpose",
    [
        LLMPurpose.CHAPTER_CLASSIFY,
        LLMPurpose.CHARACTER_EXTRACT,
        LLMPurpose.RELATION_EXTRACT,
        LLMPurpose.ADJUDICATE,
        LLMPurpose.ANSWER,
    ],
)
def test_non_judge_purposes_route_local(purpose: LLMPurpose) -> None:
    route = route_for(purpose)

    assert route.model == settings.llm_model
    assert route.base_url == settings.vllm_base_url
    assert route.frontier is False


def test_judge_refuses_local_inference_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "inference_mode", InferenceMode.LOCAL)

    with pytest.raises(PermanentLLMError, match="inference_mode=local"):
        route_for(LLMPurpose.JUDGE)


def test_judge_requires_frontier_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "inference_mode", InferenceMode.ROUTED)
    monkeypatch.setattr(settings, "frontier_model", None)

    with pytest.raises(PermanentLLMError, match="frontier_model"):
        route_for(LLMPurpose.JUDGE)


def test_judge_routes_frontier_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "inference_mode", InferenceMode.API)
    monkeypatch.setattr(settings, "frontier_model", "claude-frontier")

    route = route_for(LLMPurpose.JUDGE)

    assert route.model == "claude-frontier"
    assert route.base_url is None
    assert route.frontier is True

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


def test_mode_override_switches_a_non_judge_purpose_to_frontier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S8.2: the model ablation axis switches per call, explicitly."""
    monkeypatch.setattr(settings, "frontier_model", "claude-frontier")

    route = route_for(LLMPurpose.ANSWER, mode=InferenceMode.API)

    assert route.model == "claude-frontier"
    assert route.frontier is True

    # And the next unrelated call, without the override, is unaffected.
    default_route = route_for(LLMPurpose.ANSWER)
    assert default_route.frontier is False


def test_mode_none_is_always_local_for_a_non_judge_purpose_regardless_of_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``settings.inference_mode`` is deliberately not consulted here — see
    ``route_for``'s docstring: this repo's own dev/test default is
    ``INFERENCE_MODE=api`` with no ``FRONTIER_MODEL`` set, so wiring the
    ambient setting into the default path would break every ordinary call."""
    monkeypatch.setattr(settings, "inference_mode", InferenceMode.API)
    monkeypatch.setattr(settings, "frontier_model", "claude-frontier")

    route = route_for(LLMPurpose.ANSWER, mode=None)

    assert route.frontier is False
    assert route.model == settings.llm_model


def test_api_mode_requires_frontier_model_for_a_non_judge_purpose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "frontier_model", None)

    with pytest.raises(PermanentLLMError, match="frontier_model"):
        route_for(LLMPurpose.ANSWER, mode=InferenceMode.API)


def test_routed_mode_is_conservative_local_default_for_a_non_judge_purpose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = route_for(LLMPurpose.ANSWER, mode=InferenceMode.ROUTED)

    assert route.model == settings.llm_model
    assert route.frontier is False

import pytest

from api.config.settings import settings
from api.contracts.enums import InferenceMode, LLMPurpose
from api.llm.errors import PermanentLLMError
from api.llm.routing import (
    clear_live_policy,
    get_live_policy,
    route_for,
    set_live_policy,
)


@pytest.fixture(autouse=True)
def _reset_live_policy():
    """The live policy is process-global state (S9.6) -- never leak it across tests."""
    clear_live_policy()
    yield
    clear_live_policy()


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


# ── Residency floor (NFR-residency, ETH-4, S9.7) ─────────────────────────────


def test_inference_mode_local_blocks_a_policy_requested_frontier_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The residency floor sits below both the live policy and ``mode`` -- a
    policy PUT cannot route a purpose out of the host once the operator has
    opted out entirely. No per-book consent field exists in the frozen
    Sprint 9 contracts, so this global setting is the only lever there is
    (documented gap, see HANDOFF.md)."""
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "inference_mode", InferenceMode.LOCAL)
    monkeypatch.setattr(settings, "frontier_model", "claude-frontier")
    monkeypatch.setattr(settings, "frontier_api_key", SecretStr("test-key"))
    set_live_policy(1, {LLMPurpose.ANSWER.value: "claude-frontier"})

    route = route_for(LLMPurpose.ANSWER)

    assert route.frontier is False
    assert route.model == settings.llm_model


def test_inference_mode_local_blocks_an_explicit_api_mode_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nor can the S8.2 ablation axis's explicit ``mode=api`` override it."""
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "inference_mode", InferenceMode.LOCAL)
    monkeypatch.setattr(settings, "frontier_model", "claude-frontier")
    monkeypatch.setattr(settings, "frontier_api_key", SecretStr("test-key"))

    route = route_for(LLMPurpose.ANSWER, mode=InferenceMode.API)

    assert route.frontier is False
    assert route.model == settings.llm_model


def test_judge_refuses_local_inference_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unlike the frontier-absent fallback below, an explicit ``local``
    inference mode is a residency opt-out (NFR-residency, ETH-4) -- it must
    keep refusing outright, never quietly grading with the local model."""
    monkeypatch.setattr(settings, "inference_mode", InferenceMode.LOCAL)

    with pytest.raises(PermanentLLMError, match="inference_mode=local"):
        route_for(LLMPurpose.JUDGE)


def test_judge_falls_back_to_local_when_frontier_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S9.7: no frontier key provisioned in this environment by design (Sprint
    8's do1) — the pre-S9.7 behaviour was a hard ``PermanentLLMError`` here;
    now it falls back to local and says so, so a caller can tell a degraded
    judge score apart from a real frontier grade."""
    monkeypatch.setattr(settings, "inference_mode", InferenceMode.ROUTED)
    monkeypatch.setattr(settings, "frontier_model", None)
    monkeypatch.setattr(settings, "frontier_api_key", None)

    route = route_for(LLMPurpose.JUDGE)

    assert route.frontier is False
    assert route.model == settings.llm_model
    assert route.fallback_reason == "frontier not configured"


def test_judge_falls_back_to_local_when_key_missing_even_if_model_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model name alone is not "configured" -- without a key the call would
    just fail at the HTTP layer instead of the routing layer, which is worse:
    it looks like a real attempt instead of an unmet precondition."""
    monkeypatch.setattr(settings, "inference_mode", InferenceMode.ROUTED)
    monkeypatch.setattr(settings, "frontier_model", "claude-frontier")
    monkeypatch.setattr(settings, "frontier_api_key", None)

    route = route_for(LLMPurpose.JUDGE)

    assert route.frontier is False
    assert route.fallback_reason == "frontier not configured"


def test_judge_routes_frontier_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "inference_mode", InferenceMode.API)
    monkeypatch.setattr(settings, "frontier_model", "claude-frontier")
    monkeypatch.setattr(settings, "frontier_api_key", SecretStr("test-key"))

    route = route_for(LLMPurpose.JUDGE)

    assert route.model == "claude-frontier"
    assert route.base_url is None
    assert route.frontier is True
    assert route.fallback_reason is None


def test_mode_override_switches_a_non_judge_purpose_to_frontier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S8.2: the model ablation axis switches per call, explicitly."""
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "frontier_model", "claude-frontier")
    monkeypatch.setattr(settings, "frontier_api_key", SecretStr("test-key"))

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


def test_api_mode_falls_back_to_local_for_a_frontier_eligible_purpose_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S9.7: ``answer`` is frontier-eligible, so an unmet frontier precondition
    degrades to local instead of raising — the pre-S9.7 behaviour here was
    ``PermanentLLMError``."""
    monkeypatch.setattr(settings, "frontier_model", None)
    monkeypatch.setattr(settings, "frontier_api_key", None)

    route = route_for(LLMPurpose.ANSWER, mode=InferenceMode.API)

    assert route.frontier is False
    assert route.model == settings.llm_model
    assert route.fallback_reason == "frontier not configured"


def test_api_mode_still_raises_for_a_non_frontier_eligible_purpose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only adjudicate/answer/judge got the S9.7 fallback (see
    ``FRONTIER_ELIGIBLE_PURPOSES``) -- nothing asked for character_extract's
    behaviour to change, so it keeps the original hard failure."""
    monkeypatch.setattr(settings, "frontier_model", None)

    with pytest.raises(PermanentLLMError, match="frontier_model"):
        route_for(LLMPurpose.CHARACTER_EXTRACT, mode=InferenceMode.API)


def test_routed_mode_is_conservative_local_default_for_a_non_judge_purpose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = route_for(LLMPurpose.ANSWER, mode=InferenceMode.ROUTED)

    assert route.model == settings.llm_model
    assert route.frontier is False


# ── Live routing policy (S9.6, F7.3) ─────────────────────────────────────────


def test_no_live_policy_is_the_default_state() -> None:
    assert get_live_policy() is None


def test_live_policy_overrides_the_local_default_for_a_configured_purpose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "frontier_model", "claude-frontier")
    monkeypatch.setattr(settings, "frontier_api_key", SecretStr("test-key"))
    set_live_policy(1, {LLMPurpose.ANSWER.value: "claude-frontier"})

    route = route_for(LLMPurpose.ANSWER)

    assert route.frontier is True
    assert route.model == "claude-frontier"

    # A purpose the policy didn't mention keeps the static local default.
    other = route_for(LLMPurpose.CHARACTER_EXTRACT)
    assert other.frontier is False


def test_live_policy_pointing_at_the_local_model_is_a_local_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_live_policy(1, {LLMPurpose.ANSWER.value: settings.llm_model})

    route = route_for(LLMPurpose.ANSWER)

    assert route.frontier is False
    assert route.model == settings.llm_model


def test_live_policy_frontier_choice_falls_back_without_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A policy can be flipped to a frontier model at any time (F7.3's "live
    switching") even when no key is provisioned in this environment -- the
    switch takes effect, it just resolves through the same S9.7 fallback."""
    monkeypatch.setattr(settings, "frontier_model", None)
    monkeypatch.setattr(settings, "frontier_api_key", None)
    set_live_policy(1, {LLMPurpose.ANSWER.value: "claude-frontier"})

    route = route_for(LLMPurpose.ANSWER)

    assert route.frontier is False
    assert route.fallback_reason == "frontier not configured"


def test_explicit_mode_wins_over_the_live_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit ablation-axis ``mode`` is a deliberate per-call override for
    measurement -- it must not be silently redirected by whatever policy
    happens to be live."""
    monkeypatch.setattr(settings, "frontier_model", None)
    set_live_policy(1, {LLMPurpose.ANSWER.value: "claude-frontier"})

    route = route_for(LLMPurpose.ANSWER, mode=InferenceMode.LOCAL)

    assert route.frontier is False
    assert route.model == settings.llm_model


def test_set_live_policy_is_read_back_by_get_live_policy() -> None:
    set_live_policy(3, {"answer": "claude-frontier"})

    version, purposes = get_live_policy()

    assert version == 3
    assert purposes == {"answer": "claude-frontier"}

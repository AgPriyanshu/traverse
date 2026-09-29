"""Purpose to model policy.

Routing is by purpose, never by call site (``../AGENTS.md``): a call site
asks for ``character_extract`` and never names a model. That makes Sprint 9's
routing dashboard (F7.3) a config change against this module rather than a
refactor of every call site.
"""

import logging
from dataclasses import dataclass

from ..config import settings
from ..contracts.enums import InferenceMode, LLMPurpose
from .errors import PermanentLLMError

logger = logging.getLogger(__name__)

# The three purposes a real frontier model is ever worth paying for (S9.7):
# ``judge`` because an 8B grading its own output is not a measurement, and
# ``adjudicate``/``answer`` because they are the query-time purposes the S8.2
# model ablation axis and the S9.6 routing policy actually sweep. Missing
# frontier credentials fall back to local for exactly these three; every
# other purpose keeps the pre-S9.7 hard-failure, since nothing asked for that
# behaviour to change there and be1's extraction purposes have never been
# exercised against a frontier model in this codebase.
FRONTIER_ELIGIBLE_PURPOSES = frozenset(
    {LLMPurpose.ADJUDICATE, LLMPurpose.ANSWER, LLMPurpose.JUDGE}
)


@dataclass(frozen=True)
class ModelRoute:
    """Where a purpose is served.

    ``base_url`` is ``None`` for a frontier call, which uses the provider's
    default endpoint with an API key rather than the local vLLM base URL.
    ``fallback_reason`` is set only when a caller asked (via ``mode``, the
    live routing policy, or ``judge``'s own hard requirement) for a frontier
    model and none was actually usable, so this route was quietly downgraded
    to local instead of failing the call outright (S9.7). A caller that cares
    whether its result came from a real frontier model — the eval judge, most
    of all — should check this rather than assume ``frontier is False`` only
    ever means "local was requested".
    """

    model: str
    base_url: str | None
    frontier: bool
    fallback_reason: str | None = None


@dataclass(frozen=True)
class _LivePolicy:
    version: int
    purposes: dict[str, str]


_live_policy: _LivePolicy | None = None


def set_live_policy(version: int, purposes: dict[str, str]) -> None:
    """Install the live per-purpose policy for this process (S9.6, F7.3).

    Called by ``PUT /ops/routing-policy`` right after it persists the new
    row, and by ``GET /ops/routing-policy`` to re-sync a process that did not
    make the last write — a Celery worker and the API server are separate
    processes sharing one Postgres table, and ``route_for`` itself takes no
    session (it is called deep inside a hot, sync-looking path), so it can
    only ever see whatever was last installed here, not the table directly.
    """
    global _live_policy
    _live_policy = _LivePolicy(version=version, purposes=dict(purposes))


def get_live_policy() -> tuple[int, dict[str, str]] | None:
    """The installed policy's ``(version, purposes)``, or ``None`` if unset."""
    if _live_policy is None:
        return None
    return (_live_policy.version, dict(_live_policy.purposes))


def clear_live_policy() -> None:
    """Reset to "no policy installed" — test-only."""
    global _live_policy
    _live_policy = None


def _policy_model_for(purpose: LLMPurpose) -> str | None:
    if _live_policy is None:
        return None
    return _live_policy.purposes.get(purpose.value)


def _is_frontier_model(model: str) -> bool:
    """A policy names a model, not a mode. Local vLLM only ever serves one
    model (``settings.llm_model``); anything else names a frontier model."""
    return model != settings.llm_model


def _frontier_configured() -> bool:
    return bool(settings.frontier_model and settings.frontier_api_key)


def route_for(purpose: LLMPurpose, *, mode: InferenceMode | None = None) -> ModelRoute:
    """Resolve which model serves ``purpose``.

    Precedence, highest first:

    0. The residency floor — ``settings.inference_mode == local`` forbids
       leaving the host at all (a private upload must never reach a
       third-party API unless the user opted in — NFR-residency, ETH-4).
       Checked before ``mode`` or the live policy even run, for every
       purpose, so neither an ablation sweep nor a ``PUT
       /ops/routing-policy`` can route around it (S9.7's own DoD: "enforce
       at the client layer where it cannot be bypassed by a policy edit").
       ``judge`` still hard-fails here rather than falling back (see below);
       every other purpose falls back to local silently, the same as
       ``mode``/policy asking for frontier with no key configured.
    1. ``judge``'s own hard requirement — always frontier once residency
       allows it at all.
    2. ``mode`` — the S8.2 ablation axis, an explicit per-call override.
    3. The live routing policy (S9.6, F7.3) — the ambient per-purpose
       default a PUT to ``/ops/routing-policy`` just changed. Checked only
       when ``mode`` did not already decide the call, so a caller sweeping
       an ablation cell is never silently redirected by whatever policy
       happens to be live.
    4. The static default: local, unchanged from before S8.2/S9.

    Frontier fallback (S9.7): for ``adjudicate``/``answer``/``judge``, asking
    for frontier without a usable ``frontier_model``/``frontier_api_key`` pair
    does not raise — it falls back to local vLLM and returns a route whose
    ``fallback_reason`` is set, so a caller (especially the eval judge) can
    tell the difference between a real frontier grade and a degraded local
    one rather than trusting both equally. Every other purpose keeps the
    original hard failure; nothing exercises frontier routing for them today.

    Args:
        purpose: The call's purpose.
        mode: Overrides the local default for this call — the Sprint 8
            "model" ablation axis. ``None`` (every caller before S8.2) defers
            to the live policy, then to local.

    Returns:
        The resolved route.

    Raises:
        PermanentLLMError: ``judge`` was requested under
            ``settings.inference_mode == local`` (leaving the host is
            forbidden outright, never downgraded to a local judge score), or
            a non-frontier-eligible purpose resolved to frontier with no
            ``settings.frontier_model`` configured.
    """
    policy_model = _policy_model_for(purpose)

    if settings.inference_mode == InferenceMode.LOCAL:
        if purpose is LLMPurpose.JUDGE:
            raise PermanentLLMError(
                "purpose=judge needs a frontier model, but inference_mode=local "
                "forbids leaving the host."
            )
        # No per-book/per-project residency flag exists in the frozen Sprint
        # 9 contracts -- this global setting is the only consent lever there
        # is, unchanged in kind from before S9.7, just applied uniformly
        # instead of judge-only. A future per-upload consent field would
        # tighten this without changing the call sites (HANDOFF.md).
        return ModelRoute(
            model=settings.llm_model, base_url=settings.vllm_base_url, frontier=False
        )

    if purpose is LLMPurpose.JUDGE:
        frontier_model = (
            policy_model
            if policy_model and _is_frontier_model(policy_model)
            else settings.frontier_model
        )

        if frontier_model and _frontier_configured():
            return ModelRoute(model=frontier_model, base_url=None, frontier=True)

        logger.warning(
            "purpose=judge has no usable frontier model configured "
            "(frontier_model=%r, frontier_api_key set=%s); falling back to "
            "local vLLM. A judge score produced this way is not an "
            "independent measurement -- flag results built on this route "
            "rather than trusting them like a real frontier grade.",
            frontier_model,
            bool(settings.frontier_api_key),
        )
        return ModelRoute(
            model=settings.llm_model,
            base_url=settings.vllm_base_url,
            frontier=False,
            fallback_reason="frontier not configured",
        )

    effective_mode = InferenceMode.LOCAL if mode is None else mode
    policy_wants_frontier = policy_model is not None and _is_frontier_model(
        policy_model
    )
    wants_frontier = effective_mode == InferenceMode.API or (
        mode is None and policy_wants_frontier
    )

    if wants_frontier:
        frontier_model = (
            policy_model if policy_wants_frontier else settings.frontier_model
        )

        if frontier_model and _frontier_configured():
            return ModelRoute(model=frontier_model, base_url=None, frontier=True)

        if purpose in FRONTIER_ELIGIBLE_PURPOSES:
            logger.warning(
                "purpose=%s requested frontier routing but no frontier "
                "model/key is configured; falling back to local vLLM.",
                purpose.value,
            )
            return ModelRoute(
                model=settings.llm_model,
                base_url=settings.vllm_base_url,
                frontier=False,
                fallback_reason="frontier not configured",
            )

        if not settings.frontier_model:
            raise PermanentLLMError("mode=api requires settings.frontier_model.")

        return ModelRoute(model=settings.frontier_model, base_url=None, frontier=True)

    if effective_mode == InferenceMode.ROUTED:
        # No per-purpose complexity signal exists yet to route on, so this
        # starts as the conservative default — identical to LOCAL, since
        # JUDGE (the one purpose known to need frontier quality) is handled
        # above regardless of mode. Splitting the rest of the purposes
        # between local and frontier under "routed" is exactly what running
        # this ablation cell is for measuring, not something to guess
        # correctly up front (S8.2).
        pass

    model = (
        policy_model
        if policy_model and not _is_frontier_model(policy_model)
        else settings.llm_model
    )
    return ModelRoute(model=model, base_url=settings.vllm_base_url, frontier=False)

"""Purpose to model policy.

Routing is by purpose, never by call site (``../AGENTS.md``): a call site
asks for ``character_extract`` and never names a model. That makes Sprint 9's
routing dashboard (F7.3) a config change against this module rather than a
refactor of every call site.
"""

from dataclasses import dataclass

from ..config import settings
from ..contracts.enums import InferenceMode, LLMPurpose
from .errors import PermanentLLMError


@dataclass(frozen=True)
class ModelRoute:
    """Where a purpose is served.

    ``base_url`` is ``None`` for a frontier call, which uses the provider's
    default endpoint with an API key rather than the local vLLM base URL.
    """

    model: str
    base_url: str | None
    frontier: bool


def route_for(purpose: LLMPurpose, *, mode: InferenceMode | None = None) -> ModelRoute:
    """Resolve which model serves ``purpose``.

    ``judge`` always routes to a frontier model — an 8B grading its own
    output is not a measurement — and that requirement is refused outright
    rather than silently downgraded to the local model when it cannot be met.
    Every other purpose routes local unless ``mode`` explicitly says
    otherwise: ``settings.inference_mode`` is deliberately **not** consulted
    for the default path here (only ``judge`` reads it, unchanged from
    before S8.2) — this repo's own ``.env.example``/compose default is
    ``INFERENCE_MODE=api`` with no ``FRONTIER_MODEL`` set, so wiring the
    global setting into every purpose's default would turn every ordinary
    call into a hard failure in dev/test. ``mode`` is how the Sprint 8 model
    ablation axis (PRD Appendix A) actually switches a purpose to
    frontier/routed — explicitly, per call, never as a side effect of the
    ambient setting.

    Args:
        purpose: The call's purpose.
        mode: Overrides the local default for this call — the Sprint 8
            "model" ablation axis. ``None`` (every caller before S8.2) is
            local, unchanged. Ignored for ``judge``, which always needs a
            frontier model regardless of the ablation cell under measurement.

    Returns:
        The resolved route.

    Raises:
        PermanentLLMError: ``judge`` was requested but ``settings.inference_mode``
            is ``local`` (a private upload must never reach a third-party API
            unless routing was explicitly enabled — NFR-residency, ETH-4), or
            ``settings.frontier_model`` is unset. Also raised for a non-judge
            purpose when ``mode`` resolves to ``API`` but
            ``settings.frontier_model`` is unset.
    """
    if purpose is LLMPurpose.JUDGE:
        if settings.inference_mode == InferenceMode.LOCAL:
            raise PermanentLLMError(
                "purpose=judge needs a frontier model, but inference_mode=local "
                "forbids leaving the host."
            )

        if not settings.frontier_model:
            raise PermanentLLMError("purpose=judge requires settings.frontier_model.")

        route = ModelRoute(model=settings.frontier_model, base_url=None, frontier=True)

        return route

    effective_mode = InferenceMode.LOCAL if mode is None else mode

    if effective_mode == InferenceMode.API:
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

    return ModelRoute(
        model=settings.llm_model, base_url=settings.vllm_base_url, frontier=False
    )

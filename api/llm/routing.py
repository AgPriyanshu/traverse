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


def route_for(purpose: LLMPurpose) -> ModelRoute:
    """Resolve which model serves ``purpose``.

    ``judge`` always routes to a frontier model — an 8B grading its own
    output is not a measurement — and that requirement is refused outright
    rather than silently downgraded to the local model when it cannot be met.

    Args:
        purpose: The call's purpose.

    Returns:
        The resolved route.

    Raises:
        PermanentLLMError: ``judge`` was requested but ``settings.inference_mode``
            is ``local`` (a private upload must never reach a third-party API
            unless routing was explicitly enabled — NFR-residency, ETH-4), or
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

    route = ModelRoute(
        model=settings.llm_model, base_url=settings.vllm_base_url, frontier=False
    )

    return route

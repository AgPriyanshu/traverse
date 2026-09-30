import logging
from typing import Any, TypeVar

from langchain.messages import HumanMessage
from pydantic import BaseModel

from ..contracts.enums import InferenceMode, LLMPurpose
from .client import get_llm, semaphore
from .errors import (
    LengthLimitError,
    PermanentLLMError,
    TransientLLMError,
    classify_call_error,
)
from .routing import FRONTIER_ELIGIBLE_PURPOSES, ModelRoute, route_for
from .tracing import trace_generation

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_MAX_ATTEMPTS = 2


async def structured_call(
    prompt: str,
    schema: type[T],
    *,
    purpose: LLMPurpose,
    book_id: str | None = None,
    stage: str | None = None,
    mode: InferenceMode | None = None,
) -> T:
    """Call the model routed for ``purpose`` and parse its reply as ``schema``.

    Args:
        prompt: The full prompt; call sites build it, this module never does.
        schema: Pydantic model the reply must validate against.
        purpose: Routes the call to a model — never chosen by the call site.
        book_id: Tags the Langfuse trace for the Sprint 9 cost breakdown.
        stage: Tags the Langfuse trace with the pipeline stage that called in.
        mode: The Sprint 8 "model" ablation axis override for this call.
            ``None`` (every caller before S8.2) is local, unchanged (see
            ``routing.route_for``). Applied to both the route and the model
            instance, so the two never disagree about which endpoint
            actually answered.

    Returns:
        A validated ``schema`` instance.

    Raises:
        LengthLimitError: The reply was cut off by the model's own length
            limit (``finish_reason == "length"``) before it finished, rather
            than failing schema validation. Raised immediately, without
            spending the correction-hint retry below — that retry only grows
            the prompt, leaving less room for the answer, and would
            reproduce the identical cutoff. A caller that can shrink its own
            input should catch this and retry smaller.
        PermanentLLMError: The reply still fails schema validation on the
            second attempt.
        TransientLLMError: The call itself failed for a reason a later
            attempt could plausibly survive (network, 5xx, 429, timeout). Not
            retried here in general -- see ``errors.py``; that retry is
            Celery's job. The one exception is a frontier call for
            ``adjudicate``/``answer``/``judge`` (S9.7's circuit breaker,
            backend-2.md's DoD: "a frontier outage must degrade, not fail"):
            that gets one immediate local retry before this propagates, since
            a query-path caller has no Celery task to retry it for.
    """
    route = route_for(purpose, mode=mode)

    try:
        return await _structured_call_once(
            prompt,
            schema,
            purpose=purpose,
            book_id=book_id,
            stage=stage,
            route=route,
            mode=mode,
        )
    except TransientLLMError:
        if not route.frontier or purpose not in FRONTIER_ELIGIBLE_PURPOSES:
            raise

        logger.warning(
            "purpose=%s frontier call failed transiently; falling back to "
            "local vLLM for this call (circuit breaker, S9.7) instead of "
            "surfacing the outage to a caller with no Celery retry of its own.",
            purpose.value,
        )
        local_route = route_for(purpose, mode=InferenceMode.LOCAL)
        return await _structured_call_once(
            prompt,
            schema,
            purpose=purpose,
            book_id=book_id,
            stage=stage,
            route=local_route,
            mode=InferenceMode.LOCAL,
        )


async def _structured_call_once(
    prompt: str,
    schema: type[T],
    *,
    purpose: LLMPurpose,
    book_id: str | None,
    stage: str | None,
    route: ModelRoute,
    mode: InferenceMode | None,
) -> T:
    """One routed attempt sequence -- the pre-S9.7 body of ``structured_call``,
    unchanged apart from taking its resolved ``route`` from the caller so the
    circuit breaker above can re-run it against a forced-local route without
    re-deriving (and risking disagreeing about) which model actually answered."""
    model = get_llm(purpose, mode=mode).with_structured_output(schema, include_raw=True)

    current_prompt = prompt
    parsing_error: BaseException | None = None
    parsed: T | None = None

    async with semaphore():
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            with trace_generation(
                purpose=purpose.value,
                model=route.model,
                book_id=book_id,
                stage=stage,
            ) as generation:
                try:
                    result = await model.ainvoke([HumanMessage(current_prompt)])
                except Exception as exc:
                    raise classify_call_error(exc) from exc

                parsed = result["parsed"]
                parsing_error = result["parsing_error"]
                finish_reason = _finish_reason(result.get("raw"))

                if generation is not None:
                    generation.update(
                        output=parsed if parsing_error is None else None,
                        status_message=str(parsing_error) if parsing_error else None,
                        level="WARNING" if parsing_error else "DEFAULT",
                        metadata={
                            "purpose": purpose.value,
                            "book_id": book_id,
                            "stage": stage,
                            "attempt": attempt,
                            "finish_reason": finish_reason,
                        },
                        usage_details=_usage_details(result.get("raw")),
                    )

            if parsing_error is None and parsed is not None:
                return parsed

            if finish_reason == "length":
                raise LengthLimitError(
                    f"purpose={purpose.value} schema={schema.__name__} reply "
                    "was cut off by the model's length limit before "
                    f"finishing: {parsing_error}"
                )

            current_prompt = (
                f"{prompt}\n\n"
                "Your previous reply failed schema validation with this "
                f"error:\n{parsing_error}\n\n"
                "Reply again with JSON that satisfies the schema exactly."
            )

    raise PermanentLLMError(
        f"purpose={purpose.value} schema={schema.__name__} still invalid "
        f"after {_MAX_ATTEMPTS} attempts: {parsing_error}"
    )


def _usage_details(raw: Any) -> dict[str, int] | None:
    usage = getattr(raw, "usage_metadata", None)
    if not usage:
        return None

    return {
        "input": usage.get("input_tokens", 0),
        "output": usage.get("output_tokens", 0),
    }


def _finish_reason(raw: Any) -> str | None:
    """Read the OpenAI-compatible ``finish_reason`` off the raw reply.

    ``"length"`` means generation stopped because it ran out of context, not
    because the model chose to stop — the deterministic signal that a reply
    was truncated rather than merely schema-invalid.
    """
    metadata = getattr(raw, "response_metadata", None) or {}

    return metadata.get("finish_reason")

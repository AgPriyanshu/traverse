"""Structured JSON output with one schema-validation retry.

Qwen3-8B via vLLM's guided decoding still emits schema-invalid JSON under
load. The retry appends the validation error to the prompt rather than
silently resending the same request, and both attempts are recorded against
the same Langfuse trace — a silent retry would corrupt Sprint 9's cost
accounting (F7.1).
"""

from typing import Any, TypeVar

from langchain.messages import HumanMessage
from pydantic import BaseModel

from ..contracts.enums import LLMPurpose
from .client import get_llm, semaphore
from .errors import LengthLimitError, PermanentLLMError, classify_call_error
from .routing import route_for
from .tracing import trace_generation

T = TypeVar("T", bound=BaseModel)

_MAX_ATTEMPTS = 2


async def structured_call(
    prompt: str,
    schema: type[T],
    *,
    purpose: LLMPurpose,
    book_id: str | None = None,
    stage: str | None = None,
) -> T:
    """Call the model routed for ``purpose`` and parse its reply as ``schema``.

    Args:
        prompt: The full prompt; call sites build it, this module never does.
        schema: Pydantic model the reply must validate against.
        purpose: Routes the call to a model — never chosen by the call site.
        book_id: Tags the Langfuse trace for the Sprint 9 cost breakdown.
        stage: Tags the Langfuse trace with the pipeline stage that called in.

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
            attempt could plausibly survive (network, 5xx, 429, timeout).
            Not retried here — see ``errors.py``; that retry is Celery's job.
    """
    route = route_for(purpose)
    model = get_llm(purpose).with_structured_output(schema, include_raw=True)

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

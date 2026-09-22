"""Error classification for every ``api.llm`` call.

Subclassing the worker retry contract (``api.workers.errors``) is what makes
``autoretry_for=(TransientError,)`` catch an LLM failure without a Celery task
having to know that its failure came from ``api.llm`` at all.
"""

from openai import APIConnectionError, APIStatusError

from ..workers.errors import PermanentError, TransientError


class TransientLLMError(TransientError):
    """Network, 5xx, 429, or timeout — a later attempt could plausibly succeed."""


class PermanentLLMError(PermanentError):
    """A 400, malformed input, or a schema violation that survived one retry.

    Retrying one four times with backoff wastes twenty minutes and ends in
    the same dead letter, so these are never retried.
    """


def classify_call_error(exc: Exception) -> TransientLLMError | PermanentLLMError:
    """Map an exception raised while calling the model to the retry contract.

    A dropped connection or a timeout means vLLM or the frontier endpoint was
    unreachable for a moment; a 429 or 5xx means it was reachable but
    overloaded — both are worth a Celery retry. A 400 or any other status
    means the request itself is wrong and will fail identically next time.

    Args:
        exc: The exception raised by the underlying OpenAI-compatible client.

    Returns:
        The classified error, ready to ``raise ... from exc``.
    """
    if isinstance(exc, TransientLLMError | PermanentLLMError):
        return exc

    if isinstance(exc, APIConnectionError):
        return TransientLLMError(str(exc))

    if isinstance(exc, APIStatusError):
        if exc.status_code == 429 or exc.status_code >= 500:
            return TransientLLMError(str(exc))

        return PermanentLLMError(str(exc))

    return PermanentLLMError(str(exc))

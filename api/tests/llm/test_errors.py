import httpx
import openai
import pytest

from api.llm.errors import PermanentLLMError, TransientLLMError, classify_call_error

_REQUEST = httpx.Request("POST", "http://localhost:8080/v1/chat/completions")


def _status_error(
    status: int, cls: type[openai.APIStatusError] = openai.APIStatusError
) -> openai.APIStatusError:
    response = httpx.Response(status, request=_REQUEST)

    return cls(f"status {status}", response=response, body=None)


def test_connection_error_is_transient() -> None:
    exc = openai.APIConnectionError(request=_REQUEST)

    classified = classify_call_error(exc)

    assert isinstance(classified, TransientLLMError)


def test_timeout_error_is_transient() -> None:
    exc = openai.APITimeoutError(request=_REQUEST)

    classified = classify_call_error(exc)

    assert isinstance(classified, TransientLLMError)


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_retryable_status_is_transient(status: int) -> None:
    classified = classify_call_error(_status_error(status))

    assert isinstance(classified, TransientLLMError)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_client_status_is_permanent(status: int) -> None:
    classified = classify_call_error(_status_error(status))

    assert isinstance(classified, PermanentLLMError)


def test_unclassified_exception_defaults_permanent() -> None:
    classified = classify_call_error(ValueError("schema mismatch"))

    assert isinstance(classified, PermanentLLMError)


def test_already_classified_error_passes_through() -> None:
    original = TransientLLMError("already known")

    assert classify_call_error(original) is original

"""``structured_call`` retry and tracing behaviour.

No vLLM is running in this worktree (BRANCH.md §9 — only one GPU exists), so
these stub the model at the same boundary every other package stubs
``api.llm`` at (``api/AGENTS.md``): the chat model returned by ``get_llm``.
The retry/classification logic under test is ours; the model's own behaviour
is exercised in integration.
"""

from typing import Any

import pytest
from langchain.messages import AIMessage
from pydantic import BaseModel, ValidationError

from api.contracts.enums import LLMPurpose
from api.llm import structured as structured_module
from api.llm.errors import LengthLimitError, PermanentLLMError, TransientLLMError
from api.llm.structured import structured_call


class _Answer(BaseModel):
    value: str


class _FakeStructuredRunnable:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self._results = list(results)
        self.prompts: list[str] = []

    async def ainvoke(self, messages: list[Any]) -> dict[str, Any]:
        self.prompts.append(messages[0].content)

        return self._results.pop(0)


class _FakeChatModel:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.runnable = _FakeStructuredRunnable(results)
        self.received_schema: type[BaseModel] | None = None
        self.received_include_raw: bool | None = None

    def with_structured_output(
        self, schema: type[BaseModel], *, include_raw: bool
    ) -> _FakeStructuredRunnable:
        self.received_schema = schema
        self.received_include_raw = include_raw

        return self.runnable


def _validation_error() -> ValidationError:
    try:
        _Answer.model_validate({})
    except ValidationError as exc:
        return exc

    raise AssertionError("expected a ValidationError")


async def test_succeeds_on_first_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeChatModel(
        [
            {
                "raw": AIMessage("ok"),
                "parsed": _Answer(value="ok"),
                "parsing_error": None,
            }
        ]
    )
    monkeypatch.setattr(structured_module, "get_llm", lambda purpose: fake)

    result = await structured_call(
        "answer the question", _Answer, purpose=LLMPurpose.ANSWER
    )

    assert result == _Answer(value="ok")
    assert fake.received_include_raw is True
    assert len(fake.runnable.prompts) == 1


async def test_retries_once_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    error = _validation_error()
    fake = _FakeChatModel(
        [
            {"raw": AIMessage("bad"), "parsed": None, "parsing_error": error},
            {
                "raw": AIMessage("good"),
                "parsed": _Answer(value="good"),
                "parsing_error": None,
            },
        ]
    )
    monkeypatch.setattr(structured_module, "get_llm", lambda purpose: fake)

    result = await structured_call(
        "answer the question", _Answer, purpose=LLMPurpose.ANSWER
    )

    assert result == _Answer(value="good")
    assert len(fake.runnable.prompts) == 2
    # The retry prompt carries the validation error forward.
    assert "answer the question" in fake.runnable.prompts[1]
    assert str(error) in fake.runnable.prompts[1]


async def test_raises_permanent_after_second_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = _validation_error()
    fake = _FakeChatModel(
        [
            {"raw": AIMessage("bad"), "parsed": None, "parsing_error": error},
            {"raw": AIMessage("still bad"), "parsed": None, "parsing_error": error},
        ]
    )
    monkeypatch.setattr(structured_module, "get_llm", lambda purpose: fake)

    with pytest.raises(PermanentLLMError):
        await structured_call("answer the question", _Answer, purpose=LLMPurpose.ANSWER)

    assert len(fake.runnable.prompts) == 2


async def test_raises_length_limit_without_a_wasted_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reply cut off by the model's own length limit is not a schema
    violation the correction-hint retry could ever fix — that retry only
    grows the prompt, leaving less room for the answer, and would reproduce
    the identical cutoff. ``finish_reason == "length"`` must be caught on the
    first attempt, distinctly from ``PermanentLLMError``, so a caller that
    can shrink its own input (``api.extraction.discovery``'s batch splitting)
    can recover instead of retrying forever.
    """
    error = _validation_error()
    fake = _FakeChatModel(
        [
            {
                "raw": AIMessage(
                    "truncated mid-object",
                    response_metadata={"finish_reason": "length"},
                ),
                "parsed": None,
                "parsing_error": error,
            },
            {
                "raw": AIMessage("would never be reached"),
                "parsed": _Answer(value="unreachable"),
                "parsing_error": None,
            },
        ]
    )
    monkeypatch.setattr(structured_module, "get_llm", lambda purpose: fake)

    with pytest.raises(LengthLimitError):
        await structured_call("answer the question", _Answer, purpose=LLMPurpose.ANSWER)

    assert len(fake.runnable.prompts) == 1


async def test_call_failure_is_classified(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    import openai

    class _RaisingRunnable:
        async def ainvoke(self, messages: list[Any]) -> dict[str, Any]:
            request = httpx.Request("POST", "http://localhost:8080/v1/x")

            raise openai.APIConnectionError(request=request)

    class _RaisingChatModel:
        def with_structured_output(self, schema: type[BaseModel], *, include_raw: bool):
            return _RaisingRunnable()

    monkeypatch.setattr(
        structured_module, "get_llm", lambda purpose: _RaisingChatModel()
    )

    with pytest.raises(TransientLLMError):
        await structured_call("answer the question", _Answer, purpose=LLMPurpose.ANSWER)

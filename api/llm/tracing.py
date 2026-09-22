"""Langfuse tracing for every ``api.llm`` call.

Every call is tagged with ``purpose``, ``book_id`` and ``stage`` — Sprint 9's
cost breakdown (F7.1) reads these tags, and a call without them is invisible
spend. Import has no side effect when Langfuse is not configured: the client
is constructed lazily and only when ``settings.langfuse_enabled``, same as the
Sprint 1 prototype.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langfuse import Langfuse

from ..config import settings

_client: Langfuse | None = None


def _langfuse() -> Langfuse | None:
    global _client

    if not settings.langfuse_enabled:
        return None

    if _client is None:
        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_base_url,
        )

    return _client


@contextmanager
def trace_generation(
    *, purpose: str, model: str, book_id: str | None, stage: str | None
) -> Iterator[Any]:
    """Wrap one ``structured_call`` in a Langfuse generation.

    Yields ``None`` when Langfuse is disabled, so a call site uses one code
    path regardless of whether tracing is configured.
    """
    client = _langfuse()
    if client is None:
        yield None

        return

    with client.start_as_current_observation(
        name=f"llm.{purpose}",
        as_type="generation",
        model=model,
        metadata={"purpose": purpose, "book_id": book_id, "stage": stage},
    ) as generation:
        yield generation

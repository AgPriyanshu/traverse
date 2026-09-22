"""Chat model construction and the shared concurrency limiter.

``api/llm`` is the only place a model may be instantiated. Unlike the Sprint 1
prototype it replaces, importing this module opens no connection and builds
no client at import time — ``get_llm`` constructs one per call, which is cheap
for an HTTP client wrapper.
"""

import asyncio

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from ..config import settings
from ..contracts.enums import LLMPurpose
from .routing import route_for

_semaphore: asyncio.Semaphore | None = None


def semaphore() -> asyncio.Semaphore:
    """Return the process-wide concurrency limiter, sized from settings.

    vLLM runs ``--max-num-seqs 16``; an unbounded fan-out from a Celery worker
    just queues and times out rather than failing fast.
    """
    global _semaphore

    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.llm_max_concurrency)

    return _semaphore


def get_llm(purpose: LLMPurpose) -> ChatOpenAI:
    """Return a chat model configured for ``purpose``.

    Args:
        purpose: Routes to a model and, transitively, an endpoint. Call sites
            never choose a model directly.
    """
    route = route_for(purpose)
    api_key = settings.frontier_api_key if route.frontier else None

    model = ChatOpenAI(
        model=route.model,
        base_url=route.base_url,
        api_key=api_key or SecretStr("not-needed"),
    )

    return model

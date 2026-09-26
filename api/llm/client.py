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
_semaphore_loop: asyncio.AbstractEventLoop | None = None


def semaphore() -> asyncio.Semaphore:
    """Return the concurrency limiter for the running event loop, sized from settings.

    vLLM runs ``--max-num-seqs 16``; an unbounded fan-out from a Celery worker
    just queues and times out rather than failing fast.

    Rebuilt whenever the running loop differs from the one it was created on,
    rather than kept as a single process-wide singleton: a Celery task is a
    sync entry point wrapping ``asyncio.run(...)`` (``api/AGENTS.md``), so a
    worker child process runs a fresh event loop per task while staying the
    same process. Reusing one ``asyncio.Semaphore`` across those loops raises
    ``RuntimeError`` on its second task, since ``Semaphore.acquire`` binds to
    whichever loop first awaited it (Python 3.10+).
    """
    global _semaphore, _semaphore_loop

    loop = asyncio.get_running_loop()
    if _semaphore is None or _semaphore_loop is not loop:
        _semaphore = asyncio.Semaphore(settings.llm_max_concurrency)
        _semaphore_loop = loop

    return _semaphore


def get_llm(purpose: LLMPurpose) -> ChatOpenAI:
    """Return a chat model configured for ``purpose``.

    Args:
        purpose: Routes to a model and, transitively, an endpoint. Call sites
            never choose a model directly.
    """
    route = route_for(purpose)
    api_key = settings.frontier_api_key if route.frontier else None

    if route.frontier:
        return ChatOpenAI(
            model=route.model,
            base_url=route.base_url,
            api_key=api_key or SecretStr("not-needed"),
        )

    # Qwen3 reasons before answering unless told not to, and without a cap a
    # runaway reply fills the whole context before any JSON appears: a single
    # 1k-token chunk once produced a 15k-token completion. The cap makes a
    # runaway fail fast as a length error the caller can split and retry.
    model = ChatOpenAI(
        model=route.model,
        base_url=route.base_url,
        api_key=SecretStr("not-needed"),
        max_tokens=settings.llm_max_output_tokens,
        extra_body={
            "chat_template_kwargs": {"enable_thinking": settings.llm_enable_thinking}
        },
    )

    return model

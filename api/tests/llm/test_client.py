import asyncio

import api.llm.client as client_module
from api.llm.client import semaphore


def test_semaphore_survives_a_new_event_loop_per_call(monkeypatch):
    """Each Celery task wraps its body in its own ``asyncio.run(...)``
    (``api/AGENTS.md``), so a worker child process runs a fresh event loop per
    task while staying the same process. A semaphore kept as a single
    process-wide singleton binds to whichever loop first awaited it and raises
    on the next task's loop; ``semaphore()`` must rebuild instead.
    """
    monkeypatch.setattr(client_module, "_semaphore", None)
    monkeypatch.setattr(client_module, "_semaphore_loop", None)

    async def acquire_once() -> int:
        async with semaphore():
            pass

        return id(semaphore())

    first = asyncio.run(acquire_once())
    second = asyncio.run(acquire_once())

    assert first != second

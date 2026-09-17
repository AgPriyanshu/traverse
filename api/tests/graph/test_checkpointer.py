import asyncio
import json
import os
import signal
import sys
import uuid
from pathlib import Path

import pytest

from api.graph.checkpoint import checkpointer, connection_string, setup_checkpointer

from .checkpoint_probe import (
    INTERRUPTED_MARKER,
    RESUMED_MARKER,
    build_graph,
)

PROBE_MODULE = "api.tests.graph.checkpoint_probe"
# Alembic and the app share one import root: the repo root, one level above
# `api/`. The child process needs the same one.
IMPORT_ROOT = Path(__file__).resolve().parents[3]
STARTUP_TIMEOUT_SECONDS = 90


@pytest.fixture(scope="session", autouse=True)
async def checkpointer_schema():
    await setup_checkpointer()


def _child_env() -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{IMPORT_ROOT}{os.pathsep}{existing}" if existing else str(IMPORT_ROOT)
    )

    return env


async def _spawn(*args: str) -> asyncio.subprocess.Process:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        PROBE_MODULE,
        *args,
        cwd=str(IMPORT_ROOT / "api"),
        env=_child_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    return process


async def _read_marker(process: asyncio.subprocess.Process, marker: str) -> dict:
    """Read the child's stdout until it emits ``marker``.

    Args:
        process: The probe process.
        marker: The marker value to wait for.

    Returns:
        The decoded JSON line carrying the marker.

    Raises:
        AssertionError: If the process exits or stalls without emitting it.
    """
    assert process.stdout is not None

    async def _scan() -> dict:
        while True:
            line = await process.stdout.readline()
            if not line:
                stderr = b""
                if process.stderr is not None:
                    stderr = await process.stderr.read()
                raise AssertionError(
                    f"probe exited before {marker}: {stderr.decode(errors='replace')}"
                )
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("marker") == marker:
                return payload

    return await asyncio.wait_for(_scan(), timeout=STARTUP_TIMEOUT_SECONDS)


async def test_connection_string_is_a_libpq_url():
    dsn = connection_string()

    assert dsn.startswith("postgresql://")
    assert "+psycopg" not in dsn


async def test_a_killed_process_resumes_from_its_checkpoint():
    """S1.6 acceptance — PRD F5.1. Sprint 7's review design rests on this.

    Start the graph, hit the interrupt, SIGKILL the process, then resume from a
    brand new process and reach the end node with the pre-interrupt state
    intact.
    """
    thread_id = f"restart-{uuid.uuid4()}"
    token = str(uuid.uuid4())

    started = await _spawn(
        "start", "--thread-id", thread_id, "--token", token, "--hang"
    )
    interrupted = await _read_marker(started, INTERRUPTED_MARKER)
    assert interrupted["state"] == ["first"]

    # SIGKILL, not terminate: no shutdown hook, no flush, no chance for the
    # process to tidy up. Whatever survives is in Postgres or it is lost.
    started.send_signal(signal.SIGKILL)
    returncode = await asyncio.wait_for(started.wait(), timeout=30)
    assert returncode == -signal.SIGKILL

    resumed = await _spawn(
        "resume", "--thread-id", thread_id, "--answer", "human-said-yes"
    )
    payload = await _read_marker(resumed, RESUMED_MARKER)
    await asyncio.wait_for(resumed.wait(), timeout=30)

    assert payload["next_before_resume"] == ["second"]
    assert payload["steps"] == ["first", "second"]
    assert payload["answer"] == "human-said-yes"
    # The value written before the interrupt survived the kill — state, not
    # just control flow, came back.
    assert payload["token"] == token


async def test_interrupt_is_checkpointed_as_a_pending_task():
    thread_id = f"pending-{uuid.uuid4()}"
    token = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    async with checkpointer() as saver:
        graph = build_graph(saver)
        await graph.ainvoke({"steps": [], "token": token}, config=config)

    # A different saver instance, standing in for a different process.
    async with checkpointer() as saver:
        graph = build_graph(saver)
        state = await graph.aget_state(config)

    assert list(state.next) == ["second"]
    assert state.values["token"] == token
    assert state.tasks and state.tasks[0].interrupts


async def test_two_threads_do_not_share_state():
    threads = [f"isolated-{uuid.uuid4()}" for _ in range(2)]
    tokens = [str(uuid.uuid4()) for _ in threads]

    async with checkpointer() as saver:
        graph = build_graph(saver)
        for thread_id, token in zip(threads, tokens, strict=True):
            await graph.ainvoke(
                {"steps": [], "token": token},
                config={"configurable": {"thread_id": thread_id}},
            )

        for thread_id, token in zip(threads, tokens, strict=True):
            state = await graph.aget_state({"configurable": {"thread_id": thread_id}})
            assert state.values["token"] == token

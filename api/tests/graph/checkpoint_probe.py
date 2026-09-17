"""Runnable probe for the S1.6 checkpointer restart acceptance.

Run as ``python -m api.tests.graph.checkpoint_probe <command>``. It must be a
separate process, not a task inside the test: the acceptance is that a *killed*
process leaves a resumable checkpoint, and an in-process cancellation proves
nothing about that.
"""

import argparse
import asyncio
import json
import sys
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from api.graph.checkpoint import checkpointer

INTERRUPTED_MARKER = "PROBE_INTERRUPTED"
RESUMED_MARKER = "PROBE_RESUMED"


class ProbeState(TypedDict, total=False):
    steps: list[str]
    token: str
    answer: str


async def first(state: ProbeState) -> dict[str, Any]:
    return {"steps": [*state.get("steps", []), "first"]}


async def second(state: ProbeState) -> dict[str, Any]:
    answer = interrupt({"question": "continue?", "token": state["token"]})

    return {"steps": [*state.get("steps", []), "second"], "answer": answer}


def build_graph(saver) -> Any:
    """Compile the two-node graph with an ``interrupt()`` between the nodes.

    Args:
        saver: The checkpointer to persist state into.

    Returns:
        The compiled graph.
    """
    builder = StateGraph(ProbeState)
    builder.add_node("first", first)
    builder.add_node("second", second)
    builder.add_edge(START, "first")
    builder.add_edge("first", "second")
    builder.add_edge("second", END)

    return builder.compile(checkpointer=saver)


def _emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


async def _start(thread_id: str, token: str, hang: bool) -> None:
    config = {"configurable": {"thread_id": thread_id}}
    async with checkpointer() as saver:
        graph = build_graph(saver)
        result = await graph.ainvoke({"steps": [], "token": token}, config=config)
        _emit({"marker": INTERRUPTED_MARKER, "state": result.get("steps", [])})

    if hang:
        # Hold the process open so the test can SIGKILL it at exactly this
        # point: after the interrupt has been checkpointed, before any resume.
        while True:
            await asyncio.sleep(3600)


async def _resume(thread_id: str, answer: str) -> None:
    config = {"configurable": {"thread_id": thread_id}}
    async with checkpointer() as saver:
        graph = build_graph(saver)
        state = await graph.aget_state(config)
        result = await graph.ainvoke(Command(resume=answer), config=config)
        _emit(
            {
                "marker": RESUMED_MARKER,
                "steps": result.get("steps", []),
                "token": result.get("token"),
                "answer": result.get("answer"),
                "next_before_resume": list(state.next),
            }
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["start", "resume", "setup"])
    parser.add_argument("--thread-id", default=str(uuid.uuid4()))
    parser.add_argument("--token", default=str(uuid.uuid4()))
    parser.add_argument("--answer", default="yes")
    parser.add_argument("--hang", action="store_true")
    args = parser.parse_args()

    if args.command == "setup":
        from api.graph.checkpoint import setup_checkpointer

        asyncio.run(setup_checkpointer())
    elif args.command == "start":
        asyncio.run(_start(args.thread_id, args.token, args.hang))
    else:
        asyncio.run(_resume(args.thread_id, args.answer))


if __name__ == "__main__":
    main()

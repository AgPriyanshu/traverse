"""LangGraph gates around the two decision-bearing points of pass 2 (S7.1, F5.1).

Celery still owns the coarse pipeline and the long CPU/GPU stages (parsing,
embedding, LLM extraction) — a LangGraph checkpoint on an 1,100-chunk payload
would be real, needless serialisation cost, and none of those stages contain a
decision. Only two points in the frozen chain can turn out to be wrong in a
way a human, not a confidence threshold, should settle:

- **roster** — pass 2 (``relations.extract``) reads the project roster
  (``load_project_roster``). If alias resolution or cross-book reconciliation
  left an open identity question for this book (a suspected character
  collision, or a mid-band cross-book match), extracting against that roster
  risks keying every edge on the wrong character id.
- **conflict** — ``relations.aggregate`` may find two assertions that cannot
  both be true (``aggregate._detect_conflicts``). Projecting either into Neo4j
  before a human picks one is exactly the "coin flip" F5.1 exists to remove.

Each gate is one node, one interrupt call, one thread — keyed as
``f"{book_id}:{gate}"`` so the two gates never share a pause, and a paused
thread is findable from a book id alone (no side table). The Postgres
checkpointer (proved in Sprint 1, ``api/graph/checkpoint.py``) is what makes
the pause survive a killed worker: see ``api/tests/graph/test_checkpointer.py``
and this sprint's ``api/tests/review/test_restart_safety.py``.

A gate that finds nothing OPEN reaches ``END`` inside its own ``ainvoke`` call
and returns immediately — most books never pause here at all. That is the
point: interrupts fire at genuine ambiguity, never as a matter of course.
"""

from typing import TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt

from ..contracts.enums import ReviewTaskType
from ..db.engine import db_session
from ..graph.checkpoint import checkpointer
from . import queries

ROSTER_GATE = "roster"
CONFLICT_GATE = "conflict"

_GATE_TASK_TYPES: dict[str, tuple[ReviewTaskType, ...]] = {
    ROSTER_GATE: (ReviewTaskType.MERGE_CHARACTERS, ReviewTaskType.MERGE_ACROSS_BOOKS),
    CONFLICT_GATE: (ReviewTaskType.RESOLVE_CONFLICT,),
}


class GateState(TypedDict, total=False):
    book_id: str
    gate: str


def thread_id(book_id: UUID | str, gate: str) -> str:
    """The checkpointer thread id for one book's gate. Stable and derivable —
    a resolved task never needs to store it to find its paused thread again.
    """
    return f"{book_id}:{gate}"


async def _gate(state: GateState) -> GateState:
    task_types = _GATE_TASK_TYPES[state["gate"]]
    async with db_session() as session:
        blocking = await queries.open_blocking_task_ids(
            session, book_id=UUID(state["book_id"]), task_types=task_types
        )

    if blocking:
        # A single call, not a loop: a resumed re-execution's ``interrupt()``
        # call is answered from the one value ``Command(resume=...)``
        # supplied and falls straight through, whatever the node re-checks
        # afterwards -- verified against the pinned LangGraph version, this
        # is not "re-check and re-pause in the same invocation," it is
        # "the caller attests this is clear." ``resume_gate`` is what
        # actually re-checks, *before* deciding whether to call this at all.
        interrupt(
            {"gate": state["gate"], "book_id": state["book_id"], "task_ids": blocking}
        )

    return state


def _build() -> StateGraph:
    builder = StateGraph(GateState)
    builder.add_node("gate", _gate)
    builder.add_edge(START, "gate")
    builder.add_edge("gate", END)

    return builder


async def _compiled(saver) -> CompiledStateGraph:
    return _build().compile(checkpointer=saver)


async def pass_gate(book_id: UUID, gate: str) -> bool:
    """Run (or re-enter) one gate for a book. Returns ``True`` once it is clear.

    The common case — nothing OPEN blocks this book — completes inside this
    one call and returns ``True`` without ever pausing. A blocked book pauses
    here (checkpointed) and this returns ``False``; the caller must not
    proceed to the work this gate protects.
    """
    config = {"configurable": {"thread_id": thread_id(book_id, gate)}}
    async with checkpointer() as saver:
        graph = await _compiled(saver)
        await graph.ainvoke({"book_id": str(book_id), "gate": gate}, config=config)
        state = await graph.aget_state(config)

    return not state.next


async def resume_gate(book_id: UUID, gate: str) -> bool:
    """Re-check a paused gate after a review decision. Returns ``True`` only
    on the transition from blocked to clear — never on a gate that was never
    paused, so a caller can use the return value to decide whether to kick
    the pipeline back into motion.

    The re-check happens *before* calling ``ainvoke``, as a plain query, not
    by letting the node re-run and re-decide: a resumed node's own
    ``interrupt()`` call is answered from the value ``Command(resume=...)``
    supplies and returns immediately whatever the node's own logic re-checks
    afterwards (verified against the pinned LangGraph version — this is not a
    "poll until clear inside one invocation" primitive). So this function is
    the actual re-check; calling ``ainvoke`` at all is only how a confirmed
    clear gets recorded as such in the checkpointed state.
    """
    task_types = _GATE_TASK_TYPES[gate]
    config = {"configurable": {"thread_id": thread_id(book_id, gate)}}
    async with checkpointer() as saver:
        graph = await _compiled(saver)
        state = await graph.aget_state(config)
        if not state.next:
            return False

        async with db_session() as session:
            blocking = await queries.open_blocking_task_ids(
                session, book_id=book_id, task_types=task_types
            )
        if blocking:
            return False

        # ``resume=None`` looks like "nothing to resume" to LangGraph's own
        # command handling and crashes with an unrelated ``UnboundLocalError``
        # (checked against the pinned version); the gate never reads this
        # value; any non-``None`` sentinel works.
        await graph.ainvoke(Command(resume=True), config=config)
        state = await graph.aget_state(config)

    return not state.next


async def gate_state(book_id: UUID, gate: str) -> tuple[bool, list[str]]:
    """Return ``(is_paused, blocking_task_ids)`` for a gate without resuming it."""
    config = {"configurable": {"thread_id": thread_id(book_id, gate)}}
    async with checkpointer() as saver:
        graph = await _compiled(saver)
        state = await graph.aget_state(config)

    if not state.next or not state.tasks:
        return False, []

    blocking: list[str] = []
    for task in state.tasks:
        for value in task.interrupts:
            blocking.extend(value.value.get("task_ids", []))

    return True, blocking

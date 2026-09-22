"""Per-run and per-stage Langfuse tracing. Owned by devops engineer 1.

Every ingestion run is one Langfuse trace; every stage is a span nested under
it (S2.17). This module owns the client and the two integration points —
wiring them into `stage()` is be1's (``api/workers/stages.py``, forbidden to
do1); see ``plans/sprint-2/HANDOFF.md`` for the exact two call sites.

Per-LLM-call tracing (tagged ``purpose``/``book_id``) is a separate concern,
owned by be2's rewrite of ``api/llm.py`` (S2.7) — this module only opens the
run-level trace and the stage-level spans those calls nest under.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from langfuse import Langfuse
from langfuse.types import TraceContext

from ..config import settings
from ..contracts.enums import StageName

_client: Langfuse | None = None


def _langfuse() -> Langfuse | None:
    """``None`` when Langfuse has no keys.

    The default compose profile has no ``obs`` secrets (``docker-compose.yml``
    ``obs`` profile, BRANCH.md §4) — tracing must degrade rather than block
    ingestion, the same guard ``api/llm.py`` already applies to its own client.
    """
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


def run_trace_id(run_id: UUID) -> str:
    """A trace id stable across retries of the same run.

    Seeded on ``run_id`` so a retried run re-opens the SAME trace rather than
    fragmenting it across attempts — this mirrors ``stage()``'s own retry
    semantics (``api/workers/stages.py``: one row per run+stage, attempt
    bumped in place, never a new row per retry).
    """
    return Langfuse.create_trace_id(seed=str(run_id))


def run_trace_url(run_id: UUID) -> str | None:
    """The Langfuse UI URL for a run's trace, or ``None`` if tracing is off.

    Meant to be called once, when a run is first opened, and the result
    persisted onto ``IngestionRun.trace_url`` (already a column — see
    HANDOFF). Safe to call speculatively: it resolves the URL from the
    deterministic id alone, so it works even before the trace's first span
    has been sent.

    Talks to the Langfuse API the first time (to resolve the project id) and
    is never allowed to take ingestion down with it — any failure degrades to
    ``None``, logged, not raised.
    """
    client = _langfuse()
    if client is None:
        return None
    try:
        return client.get_trace_url(trace_id=run_trace_id(run_id))
    except Exception:
        return None


@contextmanager
def stage_span(run_id: UUID, book_id: UUID, stage: StageName) -> Iterator[None]:
    """One span per stage attempt, nested under the run's trace.

    A no-op context manager when Langfuse is disabled, so a caller never has
    to check ``settings.langfuse_enabled`` itself. Re-entering for a retried
    stage attempt opens a new span under the same trace — Langfuse has no
    notion of "replace the last span," and a retry's own span is exactly the
    signal a dead-letter view wants (S2.18), not something to hide.
    """
    client = _langfuse()
    if client is None:
        yield
        return

    try:
        with client.start_as_current_observation(
            trace_context=TraceContext(trace_id=run_trace_id(run_id)),
            name=stage.value,
            as_type="span",
            metadata={"book_id": str(book_id), "run_id": str(run_id)},
        ) as span:
            try:
                yield
            except BaseException as exc:
                span.update(level="ERROR", status_message=str(exc)[:1000])
                raise
    finally:
        client.flush()

"""Per-stage query latency instrumentation (S6.9).

be2's query pipeline (`api/query/`) wraps each stage of a single question —
route, resolve, graph, retrieve, rerank, generate, ground — in
:meth:`QueryTimer.stage`, then persists :meth:`QueryTimer.as_dict` straight
into `QueryLog.latency_ms` (`api/db/models/ops_model.py`). This module owns
only the measurement; be2 owns writing the row.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

StageLabel = Literal[
    "route", "resolve", "graph", "retrieve", "rerank", "generate", "ground"
]


class QueryTimer:
    """Wall-clock timing for one query, from construction to `as_dict()`.

    TTFT is measured against this timer's own start, not against when the
    "generate" stage begins: the gap between generation starting and the
    first token actually leaving the API — queueing, first-chunk buffering —
    is usually where the latency budget goes, and a TTFT nested inside the
    generate stage's own duration would hide exactly that gap.
    """

    def __init__(self) -> None:
        self._start = time.monotonic()
        self._stages: dict[str, int] = {}
        self._ttft_ms: int | None = None

    @contextmanager
    def stage(self, label: StageLabel) -> Iterator[None]:
        """Time one stage, accumulating into it if called more than once.

        A stage entered twice (e.g. graph-constrained retrieval falling back
        to whole-project search — query-path.md's retrieval tiers) adds to
        its running total rather than overwriting it, so the breakdown still
        sums to the true total.
        """
        started = time.monotonic()
        try:
            yield
        finally:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            self._stages[label] = self._stages.get(label, 0) + elapsed_ms

    def mark_ttft(self) -> None:
        """Record time-to-first-token, at the moment the first token leaves the API.

        Idempotent: only the first call counts, since TTFT is a single point
        in time, not a duration that could accumulate.
        """
        if self._ttft_ms is None:
            self._ttft_ms = int((time.monotonic() - self._start) * 1000)

    def as_dict(self) -> dict[str, int]:
        """Return the stage breakdown for `QueryLog.latency_ms`.

        Always includes `total_ms`; includes `ttft_ms` only if
        :meth:`mark_ttft` was called — a non-streaming or non-generating
        route (e.g. aggregation) has no first token to measure.
        """
        payload = dict(self._stages)
        if self._ttft_ms is not None:
            payload["ttft_ms"] = self._ttft_ms
        payload["total_ms"] = int((time.monotonic() - self._start) * 1000)

        return payload

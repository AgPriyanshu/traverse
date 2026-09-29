# Sprint 9 — Schema Change Requests

### SCR-1 · fe1 · 2026-09-29T04:38
**Need:** `DoneEvent` (`api/contracts/api.py`) carries no field naming which
model/route actually answered — `RouteEvent.route: QueryRoute` is the
retrieval classification (`character_lookup`/`path`/`narrative`/…), not the
inference mode, and `InferenceMode` (`api/contracts/enums.py`) is never
attached to a `QueryEvent` at all.

**Why:** S9.11 (ETH-4/NFR-residency) asks the UI to label, per answer,
whether that specific answer left the machine. Today the frontend can only
show the *currently configured policy* (`GET /ops/routing-policy`,
`components/layout/inference-mode-indicator.tsx` +
`routes/ask/inference-mode-note.tsx`, both via `@/lib/inference-mode`'s
`useEffectivePolicy`), not what actually served a past turn. Those can
diverge the moment `routed` mode's local-then-frontier-fallback (S9.7)
exists, or if the policy changes mid-session — exactly the "routed" case the
PRD's closing-argument screen is built around.

**Blocking:** no — the policy-level indicator is live today and is not
wrong, just coarser than a true per-answer label would be. S9.11's DoD
("inference mode always discoverable") is met either way.

**Proposed:** add `inference_mode: InferenceMode` (or a `frontier: bool`,
simpler) to `DoneEvent`, populated from whatever `api/llm/routing.py`'s
`route_for()` actually resolved for the `answer` purpose on that turn. The
frontend would attach it to the turn in `use-conversation.ts` and render it
per-turn in `conversation-thread.tsx`/`turn-view.tsx` instead of (or beside)
the screen-level note, closing the gap between "the policy says" and "this
answer was".

### SCR-2 · be1 · 2026-09-29T00:00
**Need:** `api/ops/upload_guard.py::sweep_expired_sessions` — the function
`scripts/sweep_upload_sessions.py` / `make upload-sweep` actually calls —
does a shallower delete than `api/pipeline/session_privacy.py`'s
`sweep_expired_upload_sessions`. It deletes the expired session's MinIO
object prefixes and then relies on Postgres `ON DELETE CASCADE` from a raw
`DELETE FROM project`, which cleans up every SQL row correctly, but never
calls `api.graph.cascade.remove_book` / `api.graph.projection.reset_project`
(the Neo4j side) or purges that book's Langfuse traces, and never sweeps
characters left orphaned by the deletion. `session_privacy.delete_book_cascade`
(and the `sweep_expired_upload_sessions` that calls it per-book) does all of
that.

**Why this is a fast-follow, not a nitpick:** S9.8 and S9.5 were built against
the same `UploadSession` table in parallel, each with its own
get-or-create/record/sweep trio, without either agent having seen the other's
finished code (see this branch's own reconciliation commit for the full
story). Session creation and per-upload recording were reconciled onto
`session_privacy`'s versions (already wired into `api/routes/books.py`,
be1-owned) in that commit. The sweep is the one piece left unreconciled: two
implementations exist, and only one is complete. `scripts/sweep_upload_sessions.py`
is the mechanism that is actually runnable today — no Celery beat service
exists in `docker-compose.yml` for `pipeline.sweep_expired_upload_sessions`'s
beat entry, which this commit removed as dead/inert rather than leave two
schedules that could later both go live and race. That makes
`scripts/sweep_upload_sessions.py` the sweep an operator will actually run
(`make upload-sweep`, cron or a systemd timer per `plans/sprint-9/HANDOFF.md`'s
prod-readiness checklist) — and today it silently leaves Neo4j nodes/edges
and Langfuse traces behind for every expired demo session once it runs.

**Blocking:** no code path calls this today (no cron/systemd timer is wired up
yet either, per the same HANDOFF checklist item), so nothing is broken in
CI or in the current deploy. It becomes a real data-leak/cleanup bug the
moment `make upload-sweep` is put on a schedule, which is listed as
outstanding prod-readiness work, not yet done.

**Proposed:** either (a) make `scripts/sweep_upload_sessions.py` call
`api.pipeline.session_privacy.sweep_expired_upload_sessions` instead of
`api.ops.upload_guard.sweep_expired_sessions` (a one-line import/call swap
plus adjusting the script's print statement to the dict return shape
`{"sessions_swept", "books_deleted"}`), or (b) delete
`upload_guard.sweep_expired_sessions` entirely and have the script import
`session_privacy`'s version directly. Either leaves exactly one sweep
implementation, which is the point. `api/ops/**` and `scripts/**` are
do1-owned (BRANCH.md), so this is filed here rather than changed directly —
happy to pair on it if that's faster than a solo pickup.

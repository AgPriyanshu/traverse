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

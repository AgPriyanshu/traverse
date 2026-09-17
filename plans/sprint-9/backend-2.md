# Sprint 9 · Backend Engineer 2

**Branch:** `ai/be2/sprint-9-routing` · **Worktree:** `../traverse-wt/be2`
**Owned:** `api/llm/**`, `api/query/**`, `api/graph/**`, `api/routes/ops.py`

---

**S9.6 Routing policy engine (F7.3).** The `purpose` enum has been in
`api/llm/routing.py` since Sprint 2 precisely so this sprint is a config feature
rather than a refactor. Cash that in.

A policy maps purpose → model, persisted and **hot-swappable without a restart**.
`PUT /api/ops/routing-policy` applies immediately; the next query uses it. The
demo's acceptance criterion is that cost per query changes measurably *within the
same session*, which a restart would break.

Every policy change is versioned with who changed it and when, and every
`query_log` row records the policy version that served it. Otherwise a cost
comparison across a policy change is uninterpretable.

**S9.7 Frontier API path (§5.1).** Route `adjudicate`, `answer`, and `judge` to a
frontier model when policy says so. Same structured-output contract as the local
path so nothing downstream branches on provider.

Requirements: timeout and circuit-breaker with fallback to local (a frontier
outage must degrade, not fail), per-purpose cost attribution, and a **hard
constraint** — a book the user uploaded privately must never reach a third-party
API unless the user explicitly enabled API routing (NFR-residency, ETH-4).
Enforce that at the client layer where it cannot be bypassed by a policy edit,
not in the policy itself.

For eval judging, use a frontier model: PRD F6.2 asks for an LLM judge, and an
8B grading its own output is not a measurement.

## DoD

- [ ] Policy hot-swaps; cost per query moves in the same session
- [ ] Policy version recorded on every query
- [ ] Circuit breaker falls back to local on frontier failure
- [ ] Residency constraint enforced below the policy layer, with a test that
      proves a private book cannot be routed out

# Sprint 9 — Standup

## be1

- **Landed:** S9.8 upload privacy (ETH-2) — session-scoped project creation,
  ownership enforcement on every book/project route, project-scoped
  content-hash dedup (fixed a real cross-project pooling bug in
  `create_book`'s fallback), and a real `DELETE /books/{id}` cascade across
  Postgres/MinIO/Langfuse/Neo4j with a 24h TTL sweep task. 13 new tests in
  `api/tests/pipeline/test_session_privacy.py`, all green; existing
  `test_books_routes.py`/`test_repository.py` still pass unchanged.
- **Next:** none — S9.9 formally deferred (see HANDOFF.md and BACKLOG.md).
- **Blocked:** not blocked, but flagging two integration-time dependencies for
  do1: no `celery beat` service exists yet to actually run the TTL sweep on a
  schedule, and live-Neo4j zero-row verification of the delete cascade still
  needs a pass against the real shared instance (be1's own tests mock the
  graph calls per BRANCH.md's Neo4j-ownership rule). Both are in HANDOFF.md.

## fe1

**Landed:** S9.10 (ops dashboard — cost/performance/health live, routing
control fixture-backed against the frozen contract, see HANDOFF.md for the
exact swap points), S9.11 (inference-mode labelling — top bar, ask screen,
upload consent gate, all off one shared `lib/inference-mode.ts`), S9.12
(accessibility pass — `jest-axe` wired in, found and fixed 3 real bugs
across the ablation table, the new percentile chart, and a 400px overflow in
the new cost-trend SVG), S9.13 (public landing at `/`, three suggested
questions into a real cited-answer conversation, upload-sandbox quota stated
up front).

**Next:** none — all four owned stories complete for this sprint.

**Blocked:** not blocked. Filed SCR-1 (non-blocking) — no `QueryEvent` field
names which inference mode served a past answer, only the current policy.

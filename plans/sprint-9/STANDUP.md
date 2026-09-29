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

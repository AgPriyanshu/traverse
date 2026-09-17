# Sprint 1 — standup

Three lines per agent per day: what landed, what is next, what is blocked.

## do1 · Day 2

- **Landed:** RabbitMQ is up at `pyamqp://guest:guest@localhost:5672//` with
  vhosts `/be1`, `/be2`, `/int` (be1 unblocked). Compose moved to the repo root
  with the full topology, behavioural healthchecks, `api/` and `web/`
  Dockerfiles, `nginx.conf` with `proxy_buffering off`, `.env.example`,
  `Makefile`, `scripts/**` and CI [S1.11–S1.15].
- **Next:** cold-start verification of the whole stack on shifted ports, then
  `make warm-models`.
- **Blocked on others:** `/health` still reports the freeze stub —
  `api/routes/ops.py` is not a do1 path, so the four-line wiring to
  `api.ops.gather_health` is filed in HANDOFF. `api/llm.py:49` still hardcodes a
  `/home/prinzz/...` cache path and breaks in every container.

---

### be2 · 2026-09-17

- **Landed:** S1.4 Neo4j driver lifecycle + `reset(book_id)` (verified against a
  real container restart), S1.5 ontology as data (32 predicates, 17 legal
  transitions), **S1.6 checkpointer restart — passing, a SIGKILLed process
  resumes with state intact**, S1.7 read APIs and the live `/graph/ontology`.
  45 tests green against the live Neo4j and the real `traverse_be2` Postgres.
- **Next:** nothing in Sprint 1; relations and upsert are Sprint 4.
- **Blocked:** nothing. SCR-1 filed (non-blocking): `GraphEdgeOut.page_refs` has
  no book dimension. One cross-boundary note for be1 — the Celery worker
  bootstrap still needs `graph.connect()` on `worker_process_init`.

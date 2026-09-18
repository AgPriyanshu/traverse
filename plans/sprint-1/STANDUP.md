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

---

### fe1 · 2026-09-18

**Landed:** S1.8 (app shell, full S1–S9 route table, theme/dark-mode,
primitives incl. `<PageRef>`), S1.9 (typed client generated from the frozen
contract, one hook per endpoint), S1.10 (library, upload with client-side
PDF/200MB validation and a real 501 error surface, ingestion stage stepper).
99 Vitest tests; `tsc --noEmit`/`lint`/`build` clean on every commit.
**Next:** nothing left in the S1 brief; available to pair on the S1.11/S1.12
CORS/proxy question in HANDOFF.md, or start early on S2 page-viewer plumbing
if the orchestrator wants that pulled forward.
**Blocked:** not blocked — four DCRs and four SCRs filed (`SCR.md`), all
non-blocking, workarounds in place and noted in code comments pointing back
at the ticket.

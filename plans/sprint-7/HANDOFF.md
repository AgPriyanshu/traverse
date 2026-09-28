# Sprint 7 — Handoff

## devops-1 — S7.11, S7.12

### S7.11 — Review-queue metrics and alerting

`api/ops/review_metrics.py` behind two new routes:

- `GET /ops/review-metrics` — queue depth by task type, open-task age
  (p50/p90/max hours), median time-to-resolve, accepted/corrected/rejected
  outcome mix, and correction rate grouped by pipeline stage.
- `GET /ops/review-alerts` — queue-depth threshold breach, tasks open >48h,
  and orphaned graph threads (a thread paused on an interrupt with no open
  review task pointing at it).

`ReviewResolution.decision` (`api/contracts/api.py`) is a freeform string with
no fixed vocabulary — S7.4 hadn't landed a resolve handler as of this writing,
so there is nothing to bucket it against yet. The accepted/corrected split is
derived instead from `CorrectionFeedback.model_value != human_value`, which is
stable regardless of what `decision` strings S7.4 ends up using. Once S7.4
lands and a real vocabulary exists, it would be worth cross-checking that the
`decision` string and the `model_value`/`human_value` diff agree — they
should, but nothing currently asserts it.

Orphaned-thread detection reads `checkpoint_writes` directly for LangGraph's
reserved `__interrupt__`/`__resume__` channels rather than compiling a graph —
see the comment on `_PAUSED_THREADS_SQL` in `review_metrics.py`. It groups by
`thread_id` only, not `(thread_id, checkpoint_ns)`; fine while nothing uses
subgraphs, worth revisiting if S7.1's ingestion graph introduces nested ones.

Two new routes bumped `api/tests/pipeline/test_books_routes.py`'s frozen path
count 43→45 (SCR-1, `plans/sprint-7/SCR.md`) — be1-owned file, do1 filed
rather than fixed it directly.

### S7.12 — Chaos testing (`scripts/chaos_test.py`, `make chaos-test`,
`.github/workflows/nightly-chaos.yml`)

Six scenarios. Same `INTEGRATION_HOST` gate as `perf_smoke.py` (S6.15):
report-only everywhere except the integration host or the nightly workflow's
own disposable GitHub Actions stack, per BRANCH.md §9. Also refuses to run
under `INTEGRATION_HOST=1` if `ingestionstage` shows a `RUNNING` row updated
in the last 10 minutes — treated as another agent's live pipeline, not a
stale row.

**Verified for real** against the shared dev stack (`INTEGRATION_HOST=1`,
containers actually killed and restarted):

- Kill `celery-worker` mid-review (via `api/tests/graph/checkpoint_probe.py`,
  Sprint 1's baseline interrupt/resume graph — S7.1's real ingestion graph
  hadn't merged as of this writing; swap the thread once it does) → **PASS**,
  state and resume value survived a real `docker compose kill`.
- Kill `db` mid-resolve → **PASS**, the pre-kill checkpoint was still on
  Postgres's volume and resumed correctly after restart.
- Kill `api` mid SSE-stream → **PASS**, a fresh query after restart answers
  normally.
- Two reviewers resolving the same task concurrently / resolving a task whose
  thread already completed → **SKIP**, `POST /api/review/tasks/{id}/resolve`
  (S7.4, be2) is still the frozen 501 stub. The script inserts a throwaway
  `reviewtask` row directly (same "not my dependency" convention as
  `test_integration_ingestion.py`'s straight-to-Postgres project creation) and
  cleans it up in a `finally`; starts asserting for real the moment S7.4 lands.
- **Network partition between the worker/api and Neo4j → FAIL, and this is a
  real finding, not a script bug**: disconnecting the `neo4j` container from
  the compose network and calling `api.graph.client.execute` from the `api`
  container hangs past a 20-second bound instead of raising a clean, fast
  error. `api/graph/client.py`'s driver has no connection/query timeout
  configured for this path. **Runbook candidate for be2**: a real network
  partition to Neo4j in production would hang whatever request triggered the
  call (a query, an upsert) rather than failing fast and letting a caller
  retry or surface an error — worth a bounded timeout on
  `driver.verify_connectivity()`/`session.run()` in `get_driver()`/`execute()`.

Two bugs found and fixed in the harness itself while verifying, worth knowing
about if you extend it:

- `docker network connect` with no `--alias` reconnects a container but drops
  its compose-assigned service-name DNS alias — every other container
  resolving it by service name (`neo4j`, not the container name) breaks
  silently afterward. The reconnect in scenario 6's `finally` now passes
  `--alias neo4j` explicitly. (Found the hard way: an earlier manual test run
  left the shared dev stack's `api`/`celery-worker` containers unable to
  resolve `neo4j` at all until reconnected with the alias restored.)
- `main()` originally collected all scenario results in one list
  comprehension — one scenario raising an uncaught exception lost every other
  scenario's already-computed result. Each scenario now runs in its own
  try/except inside the loop.
- Scenarios 1/2 need the checkpointer's `checkpoints`/`checkpoint_writes`
  tables to exist; `ensure_checkpointer_schema()` runs
  `setup_checkpointer()` once under `INTEGRATION_HOST=1` before the scenario
  loop (idempotent, same call `test_checkpointer.py`'s session fixture makes).

Not built: an SCR was not needed for S7.12 — everything it needs already
exists (Sprint 1's checkpointer, the `/health` endpoint, `/api/query`). No
hook was requested from be2; scenarios 4/5 simply skip until S7.4 lands.

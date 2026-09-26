# Sprint 5 — Schema/Shared-File Change Requests

### SCR-1 · do1 · 2026-09-26
**Need:** `api/tests/pipeline/test_books_routes.py`'s frozen route-count
assertion (`assert len(response.json()["paths"]) == 38`) needs bumping to 40.
**Why:** S5.14 added two do1-owned routes to `api/routes/ops.py`
(`GET /ops/reconciliation-quality`, `GET /ops/reconciliation-order-check`),
same class of change as SCR-3 in `plans/sprint-3/SCR.md`. do1 does not own
`api/tests/pipeline/**` (be1) and cannot edit it directly.
**Blocking:** no — same as SCR-3's precedent, this is a known, understood
test-count drift, not a real regression. Land whenever be1 next touches that
file, or batch it into the merge train.
**Proposed:** bump the literal `38` to `40` in that one assertion.

### SCR-2 · do1 · 2026-09-26
**Need:** `pipeline.reconcile_characters` (`api/pipeline/tasks.py`, be1-owned,
S5.1/S5.2) needs a per-project Postgres advisory lock
(`pg_advisory_xact_lock(hashtext(project_id::text))` or equivalent) held for
the duration of the reconcile stage.
**Why:** S5.15's acceptance criterion is "eight books ingest unattended with
no duplicate characters from races" — two books in the same project
reconciling concurrently race against the same project roster and can each
independently decide a candidate is new, creating a duplicate `Character`
row neither run alone would produce. do1 owns the orchestration
(`scripts/ingest_series.py`) and the concurrency **eval** (`eval/
identity_metrics.py`'s duplicate-rate scoring, wired to
`GET /ops/reconciliation-quality`) but cannot add the lock itself:
`api/pipeline/**` and `api/workers/**` are be1-owned, and the lock has to be
acquired inside the Celery task, not from an external script. Until it
lands, `scripts/ingest_series.py --concurrent` is a **stress-test harness
only** — it can and is expected to surface duplicates, not a proof they
cannot happen.
**Blocking:** yes for S5.15's own DoD line ("per-project reconcile lock
proven under concurrent load"), not for S5.13/S5.14, which do not depend on
it.
**Proposed:** be1 adds the advisory lock at the top of
`_reconcile_characters` in `api/pipeline/tasks.py` (or inside `api/
reconcile/`'s own entry point), released automatically at transaction end.
No schema change, no migration -- an SCR because it is a cross-agent
dependency, not because it touches a frozen file.

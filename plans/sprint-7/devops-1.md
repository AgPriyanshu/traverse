# Sprint 7 · DevOps Engineer 1

**Branch:** `ai/do1/sprint-7-chaos` · **Worktree:** `../traverse-wt/do1`
**Owned:** `eval/**`, `scripts/**`, `.github/workflows/**`, `api/ops/**`, `docker*`

## Mission

Prove the durability claims rather than asserting them, and start measuring the
review loop as a product surface with its own throughput.

---

**S7.11 Review metrics (F7.4).** Queue depth by task type, task age
distribution, median time-to-resolve, resolution outcome mix (accepted /
corrected / rejected), and **correction rate per extraction stage**.

That last one is the valuable one: a stage whose output humans correct 40% of the
time is a quality problem the automated metrics are missing, and it points
Sprint 8's calibration work at the right target.

Alert on: queue depth above threshold, any task older than 48h, a paused graph
thread with no matching open task (a state leak, and a silent one).

**S7.12 Chaos testing (F5.1).** Automate the durability claims as tests, each
asserting zero state loss and correct resume:

1. Kill the Celery worker mid-review → restart
2. Kill Postgres mid-resolve → restart
3. Kill the API during an SSE stream
4. Two reviewers resolving the same task concurrently
5. Resolve a task whose graph thread has already completed
6. Network partition between worker and Neo4j during upsert

Case 4 is the one most likely to be broken and least likely to be noticed — it
needs an idempotent resolve and a clear loser, not two half-applied merges.

Run nightly on the integration host. A chaos failure is a Sprint 8 story, not a
warning to note and move past.

*Acceptance:* All six green, running nightly, with a written runbook entry per
failure mode.

## DoD

- [ ] Review throughput and correction-rate metrics live
- [ ] Six chaos scenarios automated and green nightly
- [ ] Alerts on queue depth, task age, and orphaned threads
- [ ] Runbook covering each failure mode and its recovery

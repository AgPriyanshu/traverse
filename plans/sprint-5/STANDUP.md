# Sprint 5 standup — do1

## 2026-09-26

**Landed:** S5.13 (series corpus). Extended `scripts/seed_corpus.py` with
series metadata and a `SERIES_CORPUS` list; fetched, licensed and paginated
Anne of Green Gables (6 of 8 books — see HANDOFF.md for why 4 and 6 are
missing) and the four Sherlock Holmes novels, checksums pinned in
`corpus/manifest.json`. `scripts/seed_series.py` + `make seed-series` creates
both series projects and queues their books in order.

**Also landed:** S5.14 (reconciliation eval). Hand-labelled cross-book
identity gold set for Anne 1-3 (13 characters), `eval/identity_metrics.py`
(link P/R, false-merge rate reported separately per devops-1.md, duplicate
rate, order-independence checksum), `GET /ops/reconciliation-quality` +
`GET /ops/reconciliation-order-check`, `make eval-reconciliation`, a PR +
nightly CI workflow. Filed SCR-1 (a frozen route-count test needs bumping,
be1-owned file) and SCR-2 (S5.15 needs a per-project reconcile advisory
lock that only be1 can add, inside `api/pipeline/tasks.py`). Everything here
is real and unit-tested; the live numbers are unverified until be1's
`pipeline.reconcile_characters` (S5.1/S5.2, still a stub in this worktree)
merges — same situation S3.14 was in pre-be1-merge.

**Also landed:** S5.15 (multi-book orchestration). `scripts/ingest_series.py`
+ `make ingest-series PROJECT=<series key>` — sequential by default
(race-free regardless of SCR-2), `--concurrent` as an honest stress-test
harness, `--reverse` for the order-independence check. Per-book cost/time
report plus a roster-growth cost curve (flags superlinear pass-2 cost
growth). All three S5.13/14/15 stories are now implemented and committed.

**Next:** the full verification pass (build, targeted + full test run,
lint) requested at the end of today's session, then push.

**Blocked:** SCR-2 (per-project reconcile lock) blocks a live proof of
S5.15's concurrency DoD line, not the code itself — see SCR.md and
HANDOFF.md. Everything else in this sprint's do1 scope is unblocked.

## 2026-09-27

**Final verification pass done:** `docker compose --profile test build test`
clean; `pytest api/tests -q` → 434 passed, 1 skipped, 1 known failure
(SCR-1's frozen route count, not a regression); `ruff check`/`ruff format
--check` clean; `pnpm lint` (oxlint) clean. Fixed a lint nit found along the
way (line length in `api/ops/reconciliation_quality.py`).

**New finding:** the shared `traverse_test` Postgres database has no
per-worktree isolation (unlike `traverse_be1`/`be2`/`int`) — two concurrent
`docker compose --profile test run` invocations from different worktrees
deadlocked each other on it. Documented in HANDOFF.md and
`.agents/skills/codebase-memory/infra-topology.md`; recommend a
`TEST_POSTGRES_DB` per-worktree suffix as a Sprint 6 action item. Did not fix
in this branch (out of scope for S5.13-S5.15, found only during the final
verification pass).

All three stories (S5.13, S5.14, S5.15) are implemented, committed, and
verified. Pushing `ai/do1/sprint-5-series-corpus`.

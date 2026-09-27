# Sprint 6 — Standup

## do1 — 2026-09-27

**Landed:** S6.14 (answer quality harness) and S6.15 (latency budgets in CI),
picking up mid-session from a prior interrupted pass that had already
committed the `traverse_test`/MinIO per-worktree isolation fix
(`fix(infra): per-worktree test database and bucket isolation [S6.carried]`)
and left the eval/API/script code written but uncommitted.

- **S6.14.** 30-question gold set for Pride and Prejudice
  (`eval/gold/pride_and_prejudice/answers.yaml`, schema at
  `eval/schema/answers.schema.json`), across all six PRD query classes —
  5 single_fact, 5 relationship, 5 path, 5 aggregation, 5 temporal, 5
  unanswerable. `eval/answer_metrics.py` scores accuracy, citation precision,
  abstention rate and aggregation exact-set-match (F4.1's "exactly five
  daughters, not a plausible four") from plain gold/answered/judged data, no
  DB needed. `api/ops/answer_judge.py` is the versioned frontier-model judge
  (`answer_judge_v1`, `LLMPurpose.JUDGE` — refuses outright under
  `INFERENCE_MODE=local` rather than letting the 8B grade its own homework).
  `GET /ops/answer-quality` + `POST /ops/judge-answer` adapt a judged run into
  scores; `scripts/eval_answers.py` drives the live API end to end and writes
  `eval/gold/pride_and_prejudice/answer_judgements.json`; `make eval-answers
  BOOK=<key>` runs it and prints the table (`eval/runners/answers.py`). Added
  `.github/workflows/answer-quality.yml` (nightly, 08:30 UTC) so this actually
  trends per the DoD, same shape as `nightly-corpus.yml`.

- **S6.15.** `eval/latency_metrics.py` (p50/p95/p99, TTFT, per-stage,
  avg-cost-per-query, budget check against PRD NFR-perf: p95 <= 6s, TTFT p95
  <= 1.5s). `GET /ops/query-latency` reads `QueryLog` for a project.
  `scripts/perf_smoke.py` is the merge-train performance gate — 20 fixture
  questions, enforced (exit 1 on breach) only under `INTEGRATION_HOST=1`
  (BRANCH.md §9: a worktree shares the GPU and its timings are not a valid
  gate input), waived via `PERF_SMOKE_WAIVE=<reason>`. Wired into `make
  test-integration`, which is the merge train's gate per BRANCH.md §7 — this
  is a host script invoked by the orchestrator at merge time, not a GitHub
  Actions job (no GPU on `ubuntu-latest`, so it could never validly gate
  there). `make perf-smoke` runs it standalone.

**Also found and fixed, verifying the carried-over isolation commit:** the
new `test-db-init` service and the rewritten `scripts/bootstrap_databases.sh`
loop both used `psql -tAc "...\gexec"` — `\gexec` is only recognised by psql
when it reads a script (stdin/heredoc), and is a hard syntax error through
`-c`, not a silent no-op. This meant the per-worktree test database the prior
commit claims to create never actually got created — `docker compose
--profile test run --rm test-db-init` failed outright. Rewrote both to the
same heredoc form `docker/postgres/init/10-agent-databases.sh` already used
correctly. Verified live: `traverse_test_do1` (and `_be1`/`_be2`/`_fe1`) now
exist, `migrate-test` runs clean against `traverse_test_do1`, and `docker
compose --profile test run --rm --no-deps test` is green (see below).

**Verification (full pass, see HANDOFF for detail):** `docker compose
--profile test build test` clean (`DOCKER_CONFIG` workaround needed for a
`desktop.exe` credential-helper error, as flagged in the brief).
`docker compose --profile test run --rm --no-deps test` → **545 passed, 1
skipped, 1 known failure** (the Sprint 1-5 frozen-route-count assertion in
be1-owned `api/tests/pipeline/test_books_routes.py`, now stale at 40 paths —
S6.14/15 added 3; filed **SCR-2**, same non-blocking precedent as SCR-3/16/4
in sprints 3/4/5). `ruff check` / `ruff format --check` on `api/` clean (fixed
an unsorted-import and two E501s found along the way in the new
`api/ops/*.py` files). `GET /openapi.json` has 43 paths, includes all three
new routes, no schema errors.

**Live smoke-checked** (not just unit tests) against the shared stack:
`scripts/perf_smoke.py` against the real API — correctly reports
report-only-mode and skips cleanly (no fixture project ingested yet).
`scripts/eval_answers.py --book-key pride-and-prejudice --limit 1` — resolved
a real ingested `pride-and-prejudice` project, asked `/api/query`, got the
expected 501 ("owned by be2, S6.5"), recorded the skip, exited 0. This is the
same "lights up once the dependency lands" behaviour built into every
eval/runner in this sprint's scope.

**DoD status:**
- [x] 30-question set committed and scoring nightly
- [x] Judge prompts versioned (`answer_judge_v1`)
- [ ] 20% human spot check — cannot be done meaningfully yet: 0 questions have
      been judged in this checkout because `/api/query` isn't implemented
      (be2, S6.1-S6.5). Flagging for whoever does the spot check once a real
      judged run exists — likely late sprint, after be2 merges.
- [x] Latency gate live on the integration host (via `make test-integration`)
- [x] Cost-per-query surfaced next to latency (`avg_cost_usd` on
      `GET /ops/query-latency`) — no dedicated nightly cost/latency dashboard
      yet since `QueryLog` has no rows until be2 merges; the endpoint itself
      is ready to read them the moment it does.

**Blocked:** nothing in do1's own scope. The **numbers** this harness
produces are all zero/skip today because be2's query pipeline (S6.1-S6.5)
hasn't merged into this checkout — expected, documented, and the same
situation every prior sprint's eval work started in before its dependency
landed.

**Note for be2:** once `/api/query` and `QueryLog` land, `make eval-answers
BOOK=pride-and-prejudice` and `make perf-smoke` (or the nightly workflow) will
start producing real numbers with no code change needed here. See SCR-1
(`plans/sprint-6/SCR.md`) for the one thing that would make aggregation
scoring exact instead of proxy-matched: a `resolved_entities` field on
`DoneEvent`.

Pushing `ai/do1/sprint-6-answers`.

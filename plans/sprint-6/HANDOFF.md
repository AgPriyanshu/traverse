# Sprint 6 — Handoff

## do1 — S6.14 (answer quality) and S6.15 (latency budgets)

**What's built:**

- `eval/gold/pride_and_prejudice/answers.yaml` — 30 hand-labelled questions
  (5 per class: single_fact, relationship, path, aggregation, temporal,
  unanswerable), pinned to the corpus's `pdf_sha256` exactly like
  `roster.yaml`/`relations.yaml`. Schema at `eval/schema/answers.schema.json`.
  `eval/loaders.py` gained `load_gold_answers`/`gold_answers_path`/
  `available_gold_answer_books`, same shape as the roster/identity loaders.
- `eval/answer_metrics.py` — pure scoring functions
  (`score_answers(gold, answered, verdicts)` → `AnswerScores`): answer
  accuracy, citation precision, abstention rate, per-class accuracy, and
  aggregation exact-set-match. Key invariants, each with its own test in
  `eval/tests/test_answer_metrics.py`:
  - An abstention question never enters the accuracy pool, even if a judge
    calls the (wrong) confident answer "correct" — abstention and accuracy
    are scored independently so nothing can rescue a wrong-but-plausible
    answer through the wrong metric.
  - A question never asked is "unanswered," not silently absent or scored as
    wrong.
  - Aggregation is an **exact set** match — four of Mr Bennet's five
    daughters is a miss, not partial credit (`aggregation_misses` reports
    `missing`/`extra` per question).
- `api/ops/answer_judge.py` — the frontier-model judge. `JUDGE_PROMPT_VERSION
  = "answer_judge_v1"`, committed and versioned like a schema; bump it if the
  wording changes, since a changed prompt invalidates historical comparisons.
  Routes through `LLMPurpose.JUDGE` (`api/llm/routing.py`), which refuses
  outright under `INFERENCE_MODE=local` — the system under test is never
  allowed to grade itself.
- `api/ops/answer_quality.py` — `GET /ops/answer-quality?book_key=<key>`.
  Reads two files, not a table: the gold set and whatever
  `scripts/eval_answers.py` last wrote to
  `eval/gold/<book>/answer_judgements.json`. `gold_available=False` for a book
  with no labelled set; `answered=0` (not an error) for one never run.
- `api/ops/query_latency.py` — `GET /ops/query-latency?project_id=<id>`.
  Reads `QueryLog.latency_ms`/`cost_usd` (be1-owned model,
  `api/db/models/ops_model.py`) for the most recent 500 rows, scores via
  `eval/latency_metrics.py`. `sample_count=0` until be2 starts writing rows —
  reported as-is, not faked into a pass.
- `scripts/eval_answers.py` — drives the live API for every gold question
  (`POST /api/query`, SSE-parsed), calls the judge
  (`POST /ops/judge-answer`), writes the judgements file (resumable — a
  question already judged is skipped unless `--rejudge`), appends one line to
  `answer-quality-trend.jsonl`. A 501 from `/api/query` (be2's S6.1-S6.5 not
  merged yet) is recorded as a skip and the script exits 0, never fails a
  schedule for a dependency it doesn't own.
- `scripts/perf_smoke.py` — 20 questions against the
  `ci-integration-fixture` project, scored the same way. Only fails the build
  (`exit 1`) under `INTEGRATION_HOST=1`; everywhere else (every worktree's own
  `make test-integration`) it reports the same numbers without gating,
  because a worktree shares the one GPU vLLM singleton and its timings are
  not valid gate input (BRANCH.md §9). `PERF_SMOKE_WAIVE=<reason>` skips
  enforcement even on the integration host, for an unrelated hotfix.
  `make test-integration` now runs it as one more step in the merge-train
  gate. `make perf-smoke` runs it standalone.
- `eval/runners/answers.py` — `python3 -m eval.runners.answers --book-key
  <key>` renders the markdown table `make eval-answers` prints; same "call a
  live ops endpoint, render markdown" pattern as `eval/runners/relations.py`.
- `.github/workflows/answer-quality.yml` — nightly (08:30 UTC, after
  `nightly-corpus.yml`'s 08:00 ingestion), ingests Pride and Prejudice, runs
  `make eval-answers`, posts the table to the run summary, caches/uploads
  `answer-quality-trend.jsonl`. Green every night with an honest "0 judged"
  summary until be2 merges, same convention as `nightly-corpus.yml`.

**A real bug found and fixed in the carried-over isolation commit** (already
landed before this session started, `c84aafb`): `docker/postgres/init-test-db.sh`
and the two loops it copied into `scripts/bootstrap_databases.sh` used
`psql ... -tAc "SELECT ... WHERE NOT EXISTS (...)\gexec"`. `\gexec` is a psql
**meta-command** — it's only recognised when psql parses its input as a
script (stdin, a heredoc, `-f`), never through `-c`, where the trailing
backslash is literal text after the finished SQL statement and is a **syntax
error every time**, not a silent no-op that just happens to not fire. That
means the per-worktree `traverse_test_<worktree>` database the commit's own
message claims to create was never actually created by either the
`test-db-init` compose service or the pre-warming script — `docker compose
--profile test run --rm test-db-init` failed outright, and the first
`--profile test` run in this worktree would have failed with "database
`traverse_test_do1` does not exist," reintroducing exactly the isolation gap
the commit was meant to close. Rewrote both call sites to the same heredoc
form `docker/postgres/init/10-agent-databases.sh` already used correctly
(`psql ... <<-SQL ... \gexec ... SQL`, piped through `exec -T`/stdin rather
than `-c`). Verified live against the shared stack: `traverse_test_do1`,
`_be1`, `_be2`, `_fe1` all now exist with pgvector, `migrate-test` runs clean
against `traverse_test_do1`, and `docker compose --profile test run --rm
--no-deps test` is green. If any other worktree hit "database does not
exist" errors on `--profile test` before this fix landed, that's why — rerun
`scripts/bootstrap_databases.sh` (or just retry; `test-db-init` also runs
this fix now) after pulling this branch.

**Consumed from other agents, as documented, not yet live:**

- `LLMPurpose.JUDGE` / `structured_call` (`api/llm/structured.py`,
  `api/contracts/enums.py`) — already existed, used as-is, no changes needed.
- `QueryLog` (`api/db/models/ops_model.py`) — already existed (migration
  0010 area), used as-is.
- `POST /api/query` (be2, S6.1-S6.5) — still 501s in this checkout. Every
  script here treats that as an expected, non-failing skip.

**What be2 should know once `/api/query` lands:** `scripts/eval_answers.py`
approximates `predicted_entities` (needed for the aggregation exact-match
metric) by regex-matching the gold roster's canonical names/aliases against
the answer's own prose — noisier than reading the actually-resolved entity
set. **SCR-1** (`plans/sprint-6/SCR.md`) proposes a `resolved_entities:
list[str]` field on the frozen SSE `DoneEvent` for this; non-blocking,
batched for the Sprint 7 freeze unless S6.1-S6.5's own implementation finds
it cheaper to add now (the "graph first" retrieval order already has this
list in hand before `DoneEvent` is emitted — it's exposing it, not computing
anything new).

**What be1 (or whoever next touches `api/tests/pipeline/test_books_routes.py`)
should know:** **SCR-2** — the frozen route-count assertion needs bumping
from 40 to 43 (3 new do1 routes this sprint). Same non-blocking precedent as
SCR-3 (sprint 3), SCR-16 (sprint 4) and SCR-4 (sprint 5); do1 doesn't own that
file and can't edit it. Land at the merge train once the final count across
all four branches is known — be2's own S6.1-S6.5 routes may bump it further.

**Verification (this session, full detail):**

- `docker compose --profile test build test` — clean. Hit the documented
  `desktop.exe` credential-helper error on the first attempt; worked with
  `DOCKER_CONFIG` pointed at a temp dir holding `{}`.
- `docker compose --profile test run --rm --no-deps test` (the image's default
  command: `pytest api/tests eval/tests scripts/test_label_roster.py
  scripts/test_ingest_series.py -q`) → **545 passed, 1 skipped, 1 failed**.
  The one failure is SCR-2's known frozen-path-count drift, not a regression
  — confirmed by running `api/tests` and `eval/tests` separately too.
- `ruff check .` / `ruff format --check . --exclude db/migrations` (in
  `api/`, the only tree `make lint` actually covers — `eval/`/`scripts/` are
  not lint-gated in this repo, confirmed by pre-existing >88-char lines in
  already-committed `scripts/ingest_series.py`) — clean, after fixing one
  unsorted import and two `E501`s in the new `api/ops/*.py` files.
- `GET /openapi.json` — 43 paths (40 prior + 3 new), all three new routes
  present, no Pydantic schema errors.
- **Mid-verification incident, not caused by this session's own commands:**
  partway through the test runs, `traverse-api-1`/`celery-worker`/`web`/`db`
  on the shared stack all recreated within the same second (08:56:47-50) —
  almost certainly another agent's concurrent `docker compose up --build` on
  the same shared `traverse` compose project (BRANCH.md's documented
  "`docker compose run` from a worktree can recreate the shared db/rabbitmq
  when config differs" behaviour, `infra-topology.md`). One test run
  collided with the recreation window and produced ~121 spurious errors;
  rerunning immediately after the stack settled reproduced the clean 545/1/1
  result twice. Checked `ingestionstage` for `state='RUNNING'` on the shared
  `postgres` database both during and after — none found, and `be1`'s own
  data (`traverse_be1`, migrated, populated) was untouched. `traverse-flower-1`
  (a `docker-compose.dev.yml` dev-only observability container, unrelated to
  `--profile test`) is crash-looping with `Error: No such command 'flower'` —
  pre-existing, not touched by this session's changes, not investigated
  further (out of S6.14/S6.15 scope; flagging in case another agent needs to
  know before relying on it).

**Live smoke checks against the real shared stack** (beyond unit tests):
`scripts/perf_smoke.py` (no `INTEGRATION_HOST`) correctly reports
report-only and skips (no `ci-integration-fixture` project ingested in this
stack yet). `scripts/eval_answers.py --book-key pride-and-prejudice --limit
1` resolved a real ingested `pride-and-prejudice` project already in the
shared int database, asked `/api/query`, got the expected 501 detail ("owned
by be2, S6.5"), recorded it as skipped, exited 0.

**Next:** none outstanding for do1 in Sprint 6. Everything is implemented,
tested, and verified against real (if currently dependency-limited) live
infrastructure. Pushing `ai/do1/sprint-6-answers`.

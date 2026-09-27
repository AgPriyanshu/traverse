# Sprint 6 — Handoff

## be1 — S6.7 through S6.9

All three of be1's Sprint 6 stories are done, tested, and merged into this
branch (`ai/be1/sprint-6-resolution`). These are be2's dependencies for
S6.1-S6.6 — signatures below are stable and safe to import against.

**S6.7 — Name resolution (`api/extraction/resolution.py`).**

```python
async def resolve_names(
    session: SQLModelAsyncSession,
    project_id: UUID,
    text: str,
    *,
    conversation_characters: Sequence[UUID] | None = None,
) -> list[CharacterRef]
```

`CharacterRef` = `{character_id, canonical_name, score, method, importance_tier}`.
Project-scoped (a series project's roster spans every book in it), never an
LLM call. Cascade: exact/normalised -> honorific/name-order -> nickname ->
partial (bare surname/given name) -> fuzzy (typo tolerance) ->
conversation-anchored relative term ("her sister", needs
`conversation_characters` — that's the hook for be2's S6.6 conversation
memory to pass in). Returns candidates ranked by score, highest first;
**more than one entry at the top score is a genuine tie** — the router must
surface it as a clarifying question rather than picking the first one.
Reuses the Sprint 3 alias-cascade primitives in `api/extraction/normalization.py`.

New repository helpers it depends on, in `api/extraction/repository.py`:
`list_project_roster(session, project_id)` and
`kinship_candidates(session, *, project_id, referent_id, predicate)` (matches
either the stored direction of a `Relation` row or its ontology inverse via
`api/graph/ontology.py::inverse_of`).

**S6.8 — Quote-span locator (`api/pipeline/quotes.py`).**

```python
async def locate_quote(
    session: SQLModelAsyncSession, chunk_id: UUID, quote: str
) -> PageSpan | None
```

`PageSpan` = `{page: int, boxes: list[SpanBox]}` (`SpanBox` is the existing
S2.6 contract in `api/contracts/api.py`, same coordinate space as
`render_page`). Cascade: exact substring -> whitespace/curly-quote
normalised -> conservative fuzzy alignment (min 20 chars, 0.85 ratio) for a
one- or two-character drift. Search is scoped to the pages the chunk itself
claims (`DocumentChunk.pages`, falling back to `page_start..page_end`).
**Returns `None` when the quote cannot be located — treat that as "drop the
citation," never as "cite the chunk's first page anyway."** Zero false
positives on fabricated quotes was the acceptance bar and is what the test
suite (`api/tests/pipeline/test_quotes.py`) is built around.

Extracted `local_copy(storage_key)` (async context manager) out of
`render_page` in `api/pipeline/render.py` as a shared helper — both need a
real local file for `pypdfium2`. Added `repository.get_chunk_with_book` for
the joined chunk+book read (needs `Book.storage_key` and the chunk's page
range in one round trip on the query critical path).

**S6.9 — Latency instrumentation (`api/pipeline/timing.py`).**

```python
class QueryTimer:
    def stage(self, label: StageLabel) -> contextmanager  # accumulates, not overwrites
    def mark_ttft(self) -> None                            # idempotent, first call wins
    def as_dict(self) -> dict[str, int]                    # -> QueryLog.latency_ms
```

`StageLabel` is `Literal["route", "resolve", "graph", "retrieve", "rerank",
"generate", "ground"]`. `as_dict()` always includes `total_ms`; includes
`ttft_ms` only if `mark_ttft()` was called (a non-generating route, e.g.
aggregation, has no first token). **Call `mark_ttft()` at the point the
first token actually leaves the API, not when generation starts** — the gap
between those two is where the budget usually goes, and nesting TTFT inside
the `generate` stage's own duration would hide it.

This module only measures; be2 owns instantiating one `QueryTimer` per
query, wrapping each pipeline stage in `.stage(...)`, and persisting
`.as_dict()` into `QueryLog.latency_ms` (`api/db/models/ops_model.py`,
migration 0011).

**Not done, and not blocking:** no route in `api/routes/books.py` calls
these directly — none of S6.7-S6.9 required a route change per the sprint
plan; they're internal services for be2's query pipeline to import. If S6.1
turns out to need a thin wrapper route (e.g. for the frontend's own
debugging), that's an SCR against `api/routes/books.py`, not a scope change
here.

**Verification:** targeted tests (48) plus the full suite (489 passed, 1
pre-existing skip) both green in the `test` container; `ruff check`/`ruff
format --check` clean across `api/`. See STANDUP.md for the run details.

## fe1 — S6.10 through S6.13

Picked up an interrupted session that had already built all four stories to
a high standard (192 Vitest tests, `pnpm lint`/`typecheck`/`build` clean,
the memory map already rewritten) but hadn't committed. Verified the
existing work rather than redoing it, found and closed one real gap, then
committed and pushed.

**What was already built, verified as correct against the frozen contracts:**

- **S6.10** — `/books/:id/ask` and `/projects/:id/ask` (`<AskScreen>`, shared).
  `use-conversation.ts` drives `POST /api/query`/`POST /api/query/{id}/respond`
  via a hand-rolled SSE reader (`lib/api/query-stream.ts` — no generated
  client covers a streaming body). Tokens and citations accumulate into an
  ordered `AnswerPart[]` so a citation splices in right where its claim ends,
  not appended as a footnote. Suggested questions rank the project's own
  roster by tier/mention count, falling back to three generic prompts for an
  empty roster. Route decision shown subtly ("answered from the character
  record"). Abstentions render as a considered answer (`<StatusDot
  tone="idle">`), not an error.
- **S6.11** — citations render as `<PageRef index>`, a superscript unicode
  figure, prefetched via `pageRenderQueryOptions` the instant the
  `CitationEvent` arrives (before the click). **Found incomplete: the
  citation click-through unmounted `<AskScreen>` and a plain `useState`
  conversation was lost on browser back** — the opposite of "get back to the
  answer without losing it." Fixed with `conversation-store.ts`, a
  scope-keyed cache outside React that `use-conversation.ts` reads on mount
  and writes on every update; its unmount cleanup also turns a still-
  streaming turn into a done one before the abort, so a paused stream reads
  as an answer, not a stuck spinner or an aborted-request error. New test:
  "preserves the conversation when a citation is followed to its page and
  back" (`web/tests/ask.test.tsx`), which drives a real `router.navigate(-1)`
  against the memory router (`web/tests/render.tsx` now returns the router
  instance for tests that need it).
- **S6.12** — `<InterruptCard>` (`components/ui/interrupt-card.tsx`): a
  clarifying question as option buttons plus a free-text fallback, posts to
  `/respond`, resumes the same stream in place. Built with no `QueryEvent`/
  `ReviewTask` import so Sprint 7's review queue can reuse it unchanged, per
  the brief.
- **S6.13** — `<ConversationThread>`/`<TurnView>`: scroll-anchored, a "Copy
  answer" button per done turn. `<ScopeBanner>` always shows the
  reading-position scope the frontend itself chose (`limit_book_order`/
  `limit_chapter`) with a link to clear it back to the whole series. It does
  *not* show a carried "about Elizabeth Bennet" character scope — the
  contract has nowhere to put one yet (see SCR note below).

**Filed:** `plans/sprint-6/SCR.md` SCR-1 — `CitationOut` has no `SpanBox`, so
every ask-screen citation degrades to a plain page link (correct page, no
highlighted quote); the third contract to hit the same gap Sprint 3/4 already
filed for `MentionOut`/`EvidenceOut`. Not blocking — flagged, not worked
around, since there's no client-side substitute for a real bounding box.
Also noted (not re-filed) that do1's own SCR-1 in this sprint —
`DoneEvent` missing `resolved_entities` — is the same underlying gap
`<ScopeBanner>` would need for the character-scope banner the S6.13 brief's
example implies; whichever lands covers both consumers.

**Verification (final pass, 2026-09-27):** `docker compose --profile test
run --rm test-web` — 193 Vitest tests passing across 15 files (was 192; +1
for the back-navigation regression test), lint and typecheck clean inside
that same containerized run. `pnpm build` clean on the host
(`tsc -b && vite build`, one pre-existing >500kB chunk warning on
`graph-explorer`, not from this sprint's files). Three commits on
`ai/fe1/sprint-6-ask`, pushed:

1. `feat(web): ask screen with streaming answers, inline citations, and a
   reusable interrupt [S6.10, S6.11, S6.12, S6.13]` — the inherited work,
   committed as-is.
2. `fix(web): preserve the conversation across a citation click-through
   [S6.11]` — the gap above.
3. `docs(sprint-6): memory map for the ask screen [S6.10-S6.13]`.

**Not verified against a live be2 backend** — S6.1-S6.9 (be2/be1's router,
retrieval, grounding, streaming, conversation memory) were not merged into
this worktree at time of writing; built and tested against the frozen
`api/contracts/api.py` `QueryEvent`/`QueryRequest`/`ClarifyResponse` with
realistic SSE mocks, same pattern as every prior sprint's frontend work here.
Re-run this sprint's demo script once be2's Sprint 6 lands on `ai-master`.

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

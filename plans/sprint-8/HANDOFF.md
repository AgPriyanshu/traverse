# Sprint 8 — HANDOFF (be2)

## S8.1 — `ReadingScope` (spoiler enforcement)

See `.agents/skills/codebase-memory/query-path.md` §"Spoiler scoping —
`ReadingScope`" for the full contract. Summary for other agents:

- `api/query/scope.py::ReadingScope` — required everywhere in
  `api/query/**`, `api/graph/**`, `api/retrieval/**` below the HTTP boundary.
  `ReadingScope.unlimited()` for "no limit".
- **Measured leakage: 0/22 checks** (`api/tests/query/test_spoiler_leakage.py`).
- Known residual gap: a conversation's carried reading position
  (`Conversation.scope_book_id`/`scope_chapter`) is not read back as a
  fallback when a later turn in the same thread omits
  `limit_book_order`/`limit_chapter` on the request — that turn runs fully
  unscoped. fe1's chapter slider (S8.6) is expected to always send both on
  every request, so this was not fixed this sprint; flagged for whoever picks
  up conversation memory next.

## S8.2 — Ablation config switching

**Entry point:** `api/eval/ablation.py::resolve(config: AblationConfig) -> ResolvedAblation`.

Call this once per ablation cell, then pass the result's fields straight
through:

```python
from api.eval.ablation import resolve, AblationAxisNotOwned

resolved = resolve(config)  # config: AblationConfig, from EvalResult.config

# Retrieval axis:
retrieved = await retrieve_for_narrative(
    session, project_id=..., question=..., character_ids=..., scope=...,
    mode=resolved.retrieval_mode,  # None -> today's recommended default
)

# Model axis:
async for delta in stream_narrative_draft(
    question, chunks, project_id=..., mode=resolved.inference_mode,
):
    ...
```

`RetrievalMode` (`api/retrieval/hybrid.py`, re-exported from `api.retrieval`)
is a **progression**, matching PRD Appendix A's arrows exactly:
`VECTOR_ONLY -> BM25 -> RERANK -> GRAPH_CONSTRAINED`, each step running
everything to its left plus one more thing:

| Mode | Dense arm | Lexical arm | Rerank | Graph constraint |
|---|---|---|---|---|
| `vector_only` | yes | no | no | no |
| `bm25` | yes | yes | no | no |
| `rerank` | yes | yes | yes | no |
| `graph_constrained` | yes | yes | yes | yes (falls back to unconstrained if the constrained set is empty) |

`mode=None` (every pre-S8.2 caller) is unchanged: today's production
behaviour, not a fifth mode.

`InferenceMode` (`api/contracts/enums.py`, already frozen) is the model axis:
`LOCAL` / `API` ("frontier" in `AblationConfig.model_mode`) / `ROUTED`.
Threaded through `api.llm.routing.route_for`, `api.llm.client.get_llm`,
`api.llm.structured.structured_call`, and
`api.query.generation.stream_narrative_draft` — all take an optional `mode`
override parameter for exactly this call.

**Important:** `route_for`'s default (`mode=None`, i.e. every call site
before S8.2) is **always local for a non-`judge` purpose, regardless of
`settings.inference_mode`** — this is unchanged from before S8.2, and
deliberately not "wired up" as part of this work. This repo's own
`.env.example`/compose default is `INFERENCE_MODE=api` with no
`FRONTIER_MODEL` set; had the default path started consulting that setting,
every ordinary (non-ablation) LLM call in dev/test would start raising
`PermanentLLMError`. Only an explicit `mode=` argument switches a call —
`judge` is the one purpose that already reads `settings.inference_mode`
directly, unchanged. **`ROUTED` is currently a conservative placeholder**
when passed explicitly: identical to `LOCAL` for every purpose except
`judge` (which already forces frontier regardless of mode). No per-purpose
complexity signal exists yet to route on — splitting the rest of the
purposes between local and frontier under "routed" is exactly what running
this ablation cell is for measuring, not something to guess correctly up
front. If do1's runner needs `routed` to mean something more specific for a
demo, that policy lives
in `api/llm/routing.py::route_for`'s last branch — an SCR is not needed to
change it, it is not a schema/contract file, just flag it here first so the
change is visible.

**The `extraction` axis (`extraction_mode`, `alias_mode`,
`with_human_review`) has no switch.** `resolve()` raises
`AblationAxisNotOwned` for `config.axis == "extraction"` rather than
returning a no-op — this is deliberate, so a runner cannot mistake "be2 built
nothing here" for "this axis has no effect". Building it needs:

- `extraction_mode` (`single_pass`/`two_pass`): a switch in
  `api/pipeline/**`/`api/extraction/**` — be1-owned. No such switch exists in
  the codebase today (grepped for `single_pass`/`two_pass`/`SINGLE_PASS`: only
  the frozen `AblationConfig` field itself names it).
  `api/relations/extract.py` is currently the only extraction path; a
  single-pass alternative would be new code, not a flag on existing code.
- `alias_mode` (`string_only`/`full_cascade`): a switch in
  `api/extraction/aliases.py`'s 5-stage cascade (`character-graph.md`) — be1-
  owned. `string_only` would mean stopping after stage 1 (exact/normalised)
  instead of running honorific-stripping through LLM adjudication.
- `with_human_review`: whether the ablation run lets `api/review/**`'s gates
  actually pause (`ReviewTaskType.MERGE_*`/`RESOLVE_CONFLICT`), or bypasses
  them. `api/review/**` is not clearly assigned to any one agent in
  BRANCH.md's roster (not in be1's or be2's explicit OWNS/FORBIDDEN lists) —
  worth resolving at the next freeze; this sprint be2 touched it only for the
  minimal, mechanical `scope=ReadingScope.unlimited()` argument S8.1's
  `relations_out`/`list_evidence`/`list_mentions` signature changes required
  (three one-line additions in `api/review/payloads.py`, no behaviour
  change).

**Tests:** `api/tests/eval/test_ablation.py` (the resolver),
`api/tests/retrieval/test_hybrid_mode.py` (arm selection per mode, mocked —
no real Postgres/BGE-M3 needed), `api/tests/llm/test_routing.py` (mode
override behaviour).

## S8.3 — Confidence calibration

**Entry point:** `api/eval/calibration.py::fit_all(session)` — fits every
`ReviewTaskType` this module knows how to label
(`merge_characters`/`merge_across_books`/`confirm_relation`) plus one pooled
`"overall"` fit, persists each to `CalibrationModel`, and returns a
`{task_type: CalibrationModelOut | None}` mapping (`None` where there was not
enough labelled feedback — see `MIN_SAMPLES_TO_FIT`, currently 10). For one
task type, call `fit_and_store(session, task_type=...)` directly.

**Real numbers, measured against this worktree's actual database
(`traverse_be2`) — not fitted:**

```
$ docker compose exec -T db psql -U postgres -d traverse_be2 -c \
    "SELECT count(*) FROM correctionfeedback;"
relation "correctionfeedback" does not exist   -- migrations never run against
                                                -- this DB; traverse_be1,
                                                -- traverse_int, traverse_test_*
                                                -- all checked too: 0 rows,
                                                -- every one of them.
```

**There is no real Sprint 7 human-review feedback in this environment to
calibrate against.** `CorrectionFeedback` rows only exist once a person
resolves an actual `ReviewTask` through the frontend queue; nothing in any
agent's worktree or the integration DB has done that yet. `fit_and_store`
correctly returns `None` for every task type against real data right now —
that is the honest measurement, not a bug: `load_labelled_feedback` reports
`fitted_on_n=0`. **ECE before/after: not defined (0 samples).** Whoever runs
the Sprint 8 demo end to end (real pipeline run → real ambiguous merges → a
real reviewer resolving them) will have real rows for `fit_all` to pick up
with zero code changes.

**The mechanism itself is verified against synthetic data**
(`api/tests/eval/test_calibration.py`, 16 tests, all passing) so its
correctness is not in question — only the absence of real input is. On a
deliberately-overconfident synthetic set (50 samples, 5 confidence levels
0.5–0.9, each level's true accuracy exactly 0.2 below its stated confidence —
the textbook miscalibration shape):

| | value |
|---|---|
| `fitted_on_n` | 50 |
| `ece_before` | **0.200** |
| `ece_after` (Platt) | 0.083 |
| `ece_after` (isotonic) | **0.000** |
| `ece_after` (reported, best of the two) | 0.000 |

Isotonic regression recovers the true (monotonic, step-wise) relationship
exactly on this synthetic set because the set was constructed to be exactly
monotonic — a real feedback distribution will be noisier and isotonic's
advantage over Platt will likely narrow; `CalibrationModel` records both
`ece_after_platt`/`ece_after_isotonic` implicitly through `CalibrationFit`
(not currently separate columns on the frozen `CalibrationModel` table — only
the better of the two is persisted as `ece_after`; if do1's S8.10 published
table wants both numbers shown, that needs an SCR to add the columns, not a
code change here).

**Tests:** `api/tests/eval/test_calibration.py` — `label_correctness` per
task type/decision (including the deliberate `resolve_conflict` exclusion),
`reliability_diagram`'s ECE on hand-computable inputs, both calibrators'
monotonicity and ECE reduction, the `MIN_SAMPLES_TO_FIT` floor, and
`fit_and_store`'s persistence + versioning (a re-fit is a new version, never
an overwrite). Along the way, found and fixed a real test-isolation gap:
`api/tests/conftest.py`'s `TABLES_TOUCHED_BY_TESTS` truncate list predates
migration `0011` and was missing `calibrationmodel`/`evalresult`/`evalrun` —
version numbers were climbing across unrelated test runs. Fixed in the same
commit (three names added, shared fixture, not S8.3-specific — every agent's
tests benefit).

# Sprint 8 — do1 HANDOFF

## What landed (S8.8, S8.9, S8.10)

- `eval/ablation.py` + `scripts/run_ablation.py` (`make eval-ablation`) —
  the partial Appendix A matrix, cached, resumable, writes `EvalRun`/
  `EvalResult` (migration 0011) and `eval/ablation_runs/latest.json`.
- `api/ops/ablation.py` behind `GET /ops/eval-runs/latest` and
  `GET /ops/eval-runs/{run_id}` — read this, fe1, for S8.7's table rather
  than the JSON artifact; it's the durable, queryable copy.
- `eval/regression_gate.py` + `scripts/{collect_gate_metrics,check_regression_gate}.py`
  (`make regression-gate`) + `.github/workflows/regression-gate.yml` — the
  CI gate, demonstrated failing on real data (see below).
- `scripts/publish_ablation_readme.py` (`make eval-ablation-readme`) —
  README.md's ablation table, regenerated from the last run.

## Two real environment gaps — not silently worked around

**No frontier judge key.** `FRONTIER_MODEL`/`FRONTIER_API_KEY` are blank in
every `.env` this sprint (by design — no key has been provisioned). Every
call to `LLMPurpose.JUDGE` (`api/ops/answer_judge.py`) requires
`settings.frontier_model`, and `api/llm/routing.py::route_for` refuses it
outright rather than silently grading with the local model. Practical effect:

- Answer **accuracy** and **citation precision** report `None`, never a
  fabricated number, for every cell — verified against a real, partial S6.14
  run already sitting in the shared integration stack (19/30 Pride and
  Prejudice gold questions answered, `judge: null` on every row).
- **Abstention rate** and **aggregation exact-match** need no judge and
  *are* real numbers from that same run — aggregation exact-match is 0/4,
  which is a genuine finding (`pp-016`–`pp-019` in the gold set), not a
  placeholder. Worth a look before Sprint 9: the aggregation path is
  currently failing every gold aggregation question it has answered so far.
- **Whoever provisions a real frontier key** can re-run `make eval-ablation`
  and `make eval-answers BOOK=pride-and-prejudice` (finishing the remaining
  11/30 questions first) to get real accuracy/citation-precision numbers —
  no code change is needed, this starts asserting for real the moment the
  key exists, same pattern as every prior sprint's "not my dependency" gaps.

**be2's S8.2 (ablation config-switch) had not landed as of this run** — I
checked `../traverse-wt/be2` directly (clean tree, only the freeze commit)
rather than wait idle, per my brief. The pipeline can currently produce
exactly **one** configuration (two-pass extraction, full alias cascade,
graph-constrained retrieval, local-routed-to-vLLM model), so:

- The extraction axis's non-recommended rows (single-pass, string-only
  aliases, +human-review) are all `blocked: no ablation config-switch exists`.
- The retrieval axis's non-recommended rows (vector-only, BM25, rerank) are
  blocked the same way.
- The model axis's frontier/routed rows are blocked for a *second*,
  independent reason: `api/llm/routing.py::route_for` routes every
  non-`judge` purpose to local vLLM unconditionally — there is no frontier or
  routed answering path to switch *to* yet, regardless of a key.
- Retrieval's and model's "recommended" cells are consequently **the same
  live run**, not independently measured — there's currently no way to tell
  "graph-constrained retrieval quality" apart from "local model quality"
  because nothing yet varies one without the other.

**If S8.2 lands a config-switch entry point before this branch merges**, the
hook I need is small: something `scripts/run_ablation.py` can call per cell
before ingesting/querying — e.g. a context manager or a settings override
resolvable from an `AblationConfig` — to actually produce the alternate
configuration. Ping me (do1) or file the shape in this doc and I'll wire
`measure_extraction_cell`/`measure_answer_backed_cell` to it; the matrix
definition and caching/resumability don't need to change, only which cells
are marked `blocked_reason=None`.

## Variance — not measured this sprint

devops-1.md asks for run-to-run variance on an unchanged commit *before*
setting the gate threshold. I did not measure it: extraction/relation
quality against already-ingested data is a deterministic read (zero variance
by construction, not informative), and measuring real noise on
accuracy/citation precision needs repeated end-to-end runs through the LLM
pipeline *and* the frontier judge — the latter is the gap above, and the
former is the "GPU host overnight" cost the sprint plan already flags as the
most expensive recurring job in the project. The gate ships at the PRD's
stated 2-point threshold, unvalidated against this project's own noise.
**Retro action item:** once a frontier key exists, run the full ablation
matrix 3-5 times on an unchanged `ai-master` commit and set the threshold
from the observed spread rather than the PRD's default.

## For the orchestrator

`traverse-prd.md` Appendix A is orchestrator-owned (BRANCH.md) and out of
do1's edit scope. The real numbers now live in README.md's generated section
(same source, `eval/ablation_runs/latest.json`) — copy them across, or point
Appendix A at the README section instead of duplicating it by hand.

## Cost

Not measured this sprint. The full matrix currently only has one measurable
configuration per axis (see above), so a "cost per full matrix" number would
describe the same one run three times, not the sweep the DoD asks for. Once
S8.2 lands, re-run `make eval-ablation` and report the wall clock/cost from
that — `scripts/run_ablation.py`'s cache/resumability means a second run
against unchanged cells costs nothing, so the number to report is the first
cold run's.

## S8.8.1 fast-follow (do1) — wired to be2's landed S8.2 `resolve()`

be2's S8.2 merged (`ai-master` @ `7962b17`). `api/eval/ablation.py::resolve()`
now gives real `RetrievalMode`/`InferenceMode` switches for the retrieval and
model axes. `eval/ablation.py::build_matrix()` no longer statically blocks
those axes' non-recommended rows, and `scripts/run_ablation.py` calls
`resolve()` per cell (`measure_answer_backed_cell`, and, defensively,
`measure_extraction_cell` — see its docstring) before measuring. Re-ran `make
eval-ablation` for real against the shared `int` dev stack (`ai-master`
containers on this host, not a mock).

**What's actually independently measured now vs. still genuinely blocked:**

| Axis | Cell | Before this fast-follow | Now |
|---|---|---|---|
| Retrieval | vector-only / BM25 / +rerank | `blocked: no config-switch` | **real, independent run** (own `cache_key`, own sample) — `precision`/`citation precision` still `None` (frontier judge gap, unchanged) |
| Retrieval | graph-constrained (recommended) | same live run as model's recommended cell | **its own independent run** |
| Model | local (recommended) | same live run as retrieval's recommended cell | **its own independent run** |
| Model | routed | `blocked: no answering path exists` | **real run** — `route_for` now has a real `ROUTED` path, but it's currently defined as identical to `LOCAL` (be2's HANDOFF, deliberate placeholder), so its numbers are expected to match `local`'s, not a bug in this measurement |
| Model | frontier | `blocked: no answering path exists` | still `blocked`, but for the *correct*, current reason now: the route exists (`route_for(mode=InferenceMode.API)` no longer raises "no route"), it raises `PermanentLLMError` because `settings.frontier_model` is blank. New constant `BLOCKED_FRONTIER_MODEL` (`eval/ablation.py`) makes this distinct from `BLOCKED_FRONTIER_JUDGE` (the judge is a separate call, blocked for the same underlying reason but a different code path) |
| Extraction | all non-recommended rows | `blocked: no config-switch` | **unchanged, still blocked** — no switch exists, out of scope for this fast-follow, confirmed live: `resolve()` still raises `AblationAxisNotOwned` for `axis="extraction"` (see `measure_extraction_cell`'s canary, which would now fail loudly if that ever stopped being true) |

**Accuracy and citation precision are still `None` on every single cell.**
`FRONTIER_MODEL`/`FRONTIER_API_KEY` are still blank in this environment's
`.env` — checked directly (`api.config.settings.frontier_model is None`) —
so `POST /ops/judge-answer` 500s (`PermanentLLMError: purpose=judge requires
settings.frontier_model`) for every gold question, on every cell, exactly as
designed. No number was guessed to fill that gap. This was true before this
fast-follow and is unchanged by it; the real change is that **every cell now
has its own real, independently-run sample** (see `n` in README.md's table)
instead of every non-recommended cell reading `n=0` or two different cells
silently sharing one static judgements file.

**How the retrieval/model cells are actually measured (new in this
fast-follow, `scripts/run_ablation.py::_run_narrative_gold_set`):** rather
than re-reading `eval/gold/<book>/answer_judgements.json` (written by a
separate, manually-run `scripts/eval_answers.py` against the frozen `POST
/api/query` HTTP contract, which has no ablation-mode parameter and is
be2-owned/frozen), the runner now drives `api.query.pipeline.answer_question`
**directly, in-process**, once per cell, with
`api.query.retrieval.retrieve_for_narrative` and
`api.query.generation.stream_narrative_draft` monkeypatched (module-attribute
swap, restored in a `finally`) to force in the cell's resolved
`retrieval_mode`/`inference_mode`. Zero lines of `api/query/**` changed to do
this — `answer_question` looks those two functions up by module attribute at
call time, so the patch reaches every call site it takes. Only the
`narrative` route ever calls either function, so a `relationship`/`path`/
`aggregation`/`single_fact` gold question is unaffected by either axis,
exactly like production; only the subset that actually routes to `narrative`
differs cell to cell, which is the true, honest scope of these two axes. This
also means `scripts/eval_answers.py`'s separately-run judgements file is no
longer a prerequisite for `make eval-ablation` at all.

**Two real bugs found running this live, not worked around:**

1. **`.env.example`'s `VLLM_BASE_URL=http://localhost:8080/v1/` is wrong for
   every containerized caller** (`docker-compose.yml`'s own default is
   `http://vllm:8080/v1/`, and `docker-compose.gpu.yml` hardcodes the same).
   `localhost` inside the `api` container does not route to the `vllm`
   container, so every LLM call (including the router's `classify_question`,
   which runs regardless of `INFERENCE_MODE`/ablation cell) failed outright
   with `openai.APIConnectionError` before this fix — `POST /api/query`
   500'd on every single question in this shared stack. Fixed in
   `.env.example` (do1-owned) to `http://vllm:8080/v1/`; also fixed the local,
   gitignored `.env` used for this run. This one is a genuine, previously-
   undiscovered fix, not a workaround — every prior sprint's live query-path
   testing in this environment would have hit this, so it's worth a quick
   check of how earlier partial `answer_judgements.json` runs (e.g. the
   "19/30" in this doc's earlier section) actually got as far as they did —
   possibly a different, correctly-configured `.env` was in place at the time
   and later overwritten.
2. **`api/query/pipeline.py::_finish` raises `greenlet_spawn has not been
   called; can't call await_only() here` while persisting the query
   log/conversation turn, on *every* route, for *every* question, in this
   environment** — a real, reproducible SQLAlchemy async/lazy-load bug,
   100% reproducible via a plain `curl -X POST /api/query`, unrelated to this
   ablation's own code. It fires *after* the `token`/`citation` events are
   already yielded, so an answer's text and citations are still captured
   correctly (`scripts/run_ablation.py`'s new harness treats it exactly like
   `api/routes/query.py::_event_stream`'s own exception boundary), but the
   `done` event (and therefore the real `abstained` flag and `latency_ms`)
   never arrives. Worked around in the harness only: `abstained` is inferred
   from the answer text matching `api.query.grounding.ABSTENTION_TEXT`
   exactly (always true when `grounding.abstain()` produced it, since that
   function always pairs it with `citations=[]`) rather than trusting a
   `done` event that never comes. **Not fixed** — `api/query/pipeline.py`,
   `api/query/repository.py`, `api/query/conversation.py` are all be2-owned
   and out of this fast-follow's edit scope (BRANCH.md). This is a real
   regression risk for the actual product (conversation memory / query logs
   are silently never persisted in this environment right now), not just an
   eval-harness inconvenience — flagging loudly for be2/the orchestrator
   rather than filing a quiet SCR, since it isn't a schema/shared-file change,
   it's a bug in code do1 cannot touch.

**A third, operational finding — not a bug, a cost:** this shared dev stack's
`vllm` container runs Qwen3-8B-AWQ on CPU (no GPU profile up), and at least
one gold question (`pp-031`, "Who are Mr. and Mrs. Gardiner?",
class=`single_fact` — a graph-derived route with *no* expected narrative
generation at all) drove a single generation call past 3 minutes of
continuous, still-growing GPU-KV-cache usage before being killed by hand.
`api/llm/**` sets no request timeout anywhere (grepped `timeout` in
`api/llm/client.py`/`api/config/settings.py`: none) — a real gap that would
let one pathological question hang a production request indefinitely today,
not just this eval run. Added `QUESTION_TIMEOUT_S = 90.0` in
`scripts/run_ablation.py` (this script's own safety net only, not a fix to
`api/llm/**`) so one bad question can no longer stall an entire ablation
cell; a question that times out is recorded as unanswered, never guessed.

Because of that cost, the real run behind README.md's current table used
**`ABLATION_GOLD_SET_LIMIT=12`** (a `scripts/run_ablation.py`-only env var,
documented in `_run_narrative_gold_set`'s docstring) — 12 of the 38 Pride and
Prejudice gold questions per retrieval/model cell, not the full set. This is
an honest, explicit sample cap: it's recorded in each affected cell's
`blocked_reason`/status (`n=12` or `n=11` in the table, never silently shown
as if it were the full 38), and cells measured this way are **never written
to the on-disk cache** (`measure_answer_backed_cell` skips `save_cache` when
the env var is set) — so they can never be read back as, or block, a real
full-set run under the same `cache_key` later. Unset the env var (or just
don't set it — the default is the real, full gold set) and re-run
`make eval-ablation` once there's GPU time or more wall-clock budget to get
the full-set numbers; no code change is needed, same "starts asserting for
real" pattern as every other gap in this doc.

**Nightly CI cost, flagged, not changed:** `.github/workflows/
regression-gate.yml`'s `nightly-full-matrix` job (`timeout-minutes: 120`)
runs `make eval-ablation` unconditionally on a schedule. Before this
fast-follow, that job's retrieval/model cells were near-instant blocked
reads; now four of them (`vector_only`/`bm25`/`rerank`/`graph_constrained`)
plus two model cells (`local`/`routed`) each drive a real, LLM-backed gold-
set pass. On this host's CPU-only vLLM, a 12-question capped sample across
those six cells took several minutes; the *full* 38-question set, uncapped,
at the `pp-031`-style worst case, could plausibly approach or exceed the
120-minute budget on a similarly GPU-less CI runner. I did not change the
workflow's timeout or add `ABLATION_GOLD_SET_LIMIT` to it — guessing a new
number for a CI-only cost I haven't measured on CI's actual hardware would be
exactly the kind of fabricated number this sprint's rules forbid. Whoever
owns the nightly runner's GPU/timeout budget should look at this before it
next fires on a real schedule.

**Variance — still not measurable, for the same reason as before, checked
directly rather than assumed:** every retrieval/model cell's `accuracy`/
`citation precision` is `None` (frontier judge gap, above) — there is no
numeric quality score to compute run-to-run spread over yet, wiring the real
cells didn't change that, and it wouldn't have: the judge is the actual
blocker, not the config-switch. What *did* become newly visible: the
retrieval axis's recommended cell (`graph_constrained`) and the model axis's
recommended cell (`local`) are, per PRD Appendix A, the *same* underlying
configuration, but are now two independently-executed 12-question runs
(different `cache_key`s, different LLM calls) rather than one shared file —
a crude proxy for run-to-run noise exists the moment there's a real number to
compare (right now both report `n=12`, `accuracy=None`, so there's nothing to
diff yet). Once a frontier key exists, comparing those two cells' `accuracy`
numbers on an unchanged commit is a free, zero-extra-cost variance sample
this fast-follow's wiring now provides, on top of the retro action item
already on file (run the full matrix 3-5 times).

**Tests:** `eval/tests/test_ablation.py` updated for the new, no-longer-
statically-blocked retrieval/model rows (dropped the stale
`test_model_axis_frontier_and_routed_cells_are_blocked`, added
`test_model_and_retrieval_axis_non_recommended_cells_are_not_statically_blocked`).
`scripts/test_run_ablation.py` unchanged and still green. Full suite
(`api/tests eval/tests scripts/test_label_roster.py
scripts/test_ingest_series.py scripts/test_run_ablation.py
scripts/test_regression_gate_cli.py scripts/test_publish_ablation_readme.py`)
via `docker compose --profile test run --rm test`: 779 passed, 1 skipped
(pre-existing), same as before this fast-follow.

# Sprint 8 — fe1 HANDOFF

## S8.6 — checked be2's `ai/be2/sprint-8-spoiler-calibration` before finishing; one real follow-up

The persistent reading-position slider (`web/src/components/spoiler/`,
`ProjectLayout`) is built against `limit_book_order`/`limit_chapter`: two
independently optional `int | None` query params on
`GET /api/projects/{id}/graph`, `GET /api/projects/{id}/characters`,
`GET /api/characters/{id}`, `GET /api/characters/{id}/mentions`, and
`QueryRequest.limit_book_order`/`limit_chapter`.

**be2 landed S8.1 (`b796938`, "required ReadingScope enforces spoiler cutoff
everywhere") on their branch while this was being built.** Checked the actual
commit, not just the branch name: `ReadingScope` (`api/query/scope.py`) is
built at the route boundary from those exact same two query params
(`ReadingScope(book_order=limit_book_order, chapter=limit_chapter)`) — **the
wire shape is unchanged**, so nothing above needs updating once that branch
merges.

**What did change, and matters for fe1 the moment it merges to `ai-master`:**
`limit_book_order`/`limit_chapter` are now *also* accepted (and enforced) on
four endpoints that never had them before — `GET
/characters/{id}/neighbourhood`, `GET /relations/arc`, `GET
/relations/{id}/evidence`, and `GET /graph/path`. The frontend hooks for all
four (`useNeighbourhood`, `useRelationArc`, `useEvidence`, `useGraphPath` in
`web/src/lib/api/hooks.ts`) predate this and **do not send the reading
position** — `useEvidence` already forwards a generic `params` object
(nothing to change there beyond the call site), but `useNeighbourhood`/
`useRelationArc`/`useGraphPath` don't even accept params yet. Concretely,
`routes/project/graph/evidence-panel.tsx`/`evidence-item.tsx` (evidence
quotes — literal citations) and `relation-arc.tsx` (a pair's relationship
across chapters — literally "how did this change over time") are surfaces
the S8.6 brief's "nothing from chapter 6+ present as node, edge, or citation"
covers and this build did not close, because the server had nowhere to
enforce it until this commit.

**Action once be2 merges:** rebase, `pnpm gen:api` (schema.d.ts doesn't have
these four endpoints' new params yet — checked, they're absent as of this
writing), then thread `limit_book_order`/`limit_chapter` from
`useReadingPositionContext()` through `useEvidence`'s existing `params`, and
add a `params` argument to `useNeighbourhood`/`useRelationArc`/`useGraphPath`
the same way `useCharacter` already does it, then pass them from
`evidence-panel.tsx` and `relation-arc.tsx`. Not done in this sprint's
S8.6 commit because the backend enforcement didn't exist yet when that work
started and landed mid-sprint — flagging rather than guessing at an unmerged
branch's contract.

None of this touches the slider's own model (`SeriesPosition`,
`buildPositionSteps`, `localStorage`) — that's a pure frontend concept and is
shape-agnostic to how the API spells "the reading position" on the wire.

## For do1 (S8.8 — the ablation runner) and be2 (S8.2/S8.3)

`/ops/evals` (`web/src/routes/ops/evals/`) renders the ablation table,
calibration chart, and metric trend, built against the frozen
`EvalRunOut`/`EvalResultOut`/`AblationConfig`/`MetricSet`/
`CalibrationModelOut` contracts — but **there is no live route serving them
yet** as of this commit. `openapi-typescript` only generates a schema for a
type some route actually returns, so with no route, there's nothing to
generate; `web/src/routes/ops/evals/types.ts` hand-mirrors the five contract
classes field-for-field instead (comment at the top explains why this is an
exception to "never hand-write API types"), and `fixtures.ts` stands in with
three runs of realistic-looking, entirely invented numbers.

**When a real route lands**, the swap is contained to `evals-screen.tsx`'s
two imports — `EVAL_RUNS`/`LATEST_RUN` and `CALIBRATION` from `./fixtures` —
everything downstream (`AblationTable`, `CalibrationChart`,
`MetricTrendChart`, `MetricDrawer`, `ablation-config.ts`'s helpers) already
renders off the typed contract shape, not the fixture module. Once the route
exists, also delete `types.ts` and import the generated `Schemas["EvalRunOut"]`
etc. from `@/lib/api` instead (regenerate via `pnpm gen:api` first).

A few assumptions this screen makes that the real route should either match
or tell fe1 to change:

- **One `GET` returns (at least) the latest run**, `EvalRunOut`-shaped, with
  `results` populated — the table groups those by `axis` client-side.
  `EVAL_RUNS` (plural, sorted by `created_at`) feeds the trend chart; if the
  real API only ever returns the latest run, the trend chart needs a second
  endpoint or a `?history=` param rather than inventing one.
- **`EvalResultOut.book_key`** is rendered as a plain string label in the
  drill-down drawer — there's no contract link from it to a `Book`/`Project`
  id, so it isn't a citation or a clickable reference anywhere on this screen.
- **`CalibrationModelOut` is fetched/rendered as a separate concern**, not
  nested inside `EvalRunOut` — the contract doesn't nest it either, so this
  should already match, but flagging it in case the real route composes them
  together.
- **"Recommended" and "baseline" are derived structurally** from
  `AblationConfig`'s own fields (`ablation-config.ts`'s `isRecommended`/
  `isBaseline`), matching PRD Appendix A's named recommendation per axis —
  not read off any contract field, since there isn't one. If the runner adds
  an explicit `is_recommended`/`is_baseline` flag, prefer that over the
  structural guess.
- **No per-question breakdown** — `EvalResultOut` is one aggregate `MetricSet`
  per matrix cell, not a list of question-level results, so "drill into a
  cell" (frontend-1.md's brief) surfaces the full `MetricSet` (every field,
  including the ones the table's headline columns omit) rather than a
  per-question table. If a per-question contract lands, `metric-drawer.tsx`
  is where that list would go.

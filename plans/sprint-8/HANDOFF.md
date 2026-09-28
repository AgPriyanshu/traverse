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

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

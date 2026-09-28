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

(filled in once landed — see commit for this story)

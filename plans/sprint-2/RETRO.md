# Sprint 2 Retrospective

**Dates:** 2026-09-18 → (in progress)
**Goal:** Upload a real novel PDF and watch every stage complete, ending with
chapters, chunks, and embeddings in Postgres — each chunk carrying page
provenance you can click through to the rendered page.
**Outcome:** (be2 section only — be1/fe1/do1/orchestrator to fill in at Day 5)

This file currently holds only be2's stories (S2.7–S2.10). The full-team
sections (Delivered table, demo result, action items) are Day-5 material per
BRANCH.md §6/§11 — filling those in alone would be guessing at three other
agents' days.

---

## be2 stories

| Story | Status | PRD ref | Notes |
|---|---|---|---|
| S2.7 — `api/llm/` substrate | Done | — | `client.py`/`errors.py`/`routing.py`/`tracing.py` were already written by an interrupted prior session; verified against the brief and kept. Added `structured.py`, `budget.py`, the package `__init__.py`, deleted the Sprint 1 `api/llm.py` prototype. |
| S2.8 — token-budget batcher | Done, Day 1 (ahead of the Day-4 deadline) | PRD §5.2 | `plan_batches` in `api/llm/budget.py`. Real Qwen3-8B tokenizer (`transformers.AutoTokenizer`, offline from the shared HF cache), not a chars/4 estimate. |
| S2.9 — hybrid retrieval | Done | F4.1 | `api/retrieval/{repository,hybrid}.py`, `GET /api/search` wired for real. Measured, not asserted — see below. |
| S2.10 — reranker behind a flag | Done, default off | PRD §5.1 | `api/retrieval/rerank.py`. Measured, not inherited — see below. |

---

## S2.9 — hybrid retrieval, measured

15-question smoke set: `api/tests/fixtures/retrieval_smoke.json` — a synthetic
20-chunk corpus (Pride-and-Prejudice-flavoured, not the real text) with 15
queries and hand-labelled relevant chunk keys. Reproduced by
`api/tests/retrieval/test_hybrid.py::test_both_arms_return_sane_results_and_rrf_is_measured`
(run with `-s` to see the printed numbers; real Postgres, real BGE-M3
embeddings on CPU, no mocks).

| Arm | recall@5 |
|---|---|
| Dense only | 1.000 |
| Lexical only | 0.067 |
| RRF (dense + lexical, k=60) | 1.000 |

**Finding, not buried:** RRF does not *beat* either arm on this smoke set —
it ties dense's ceiling. The reason is the smoke set itself: every query was
written as a paraphrase of its source chunk (e.g. "Why was Jane unwell after
her visit to Netherfield?" against a chunk that says "fell ill... in the
pouring rain", never "unwell"), so `ts_rank_cd` has almost no lexical overlap
to work with — lexical recall@5 of 0.067 means only one of fifteen queries
got a relevant hit into the lexical arm's top 5 at all. Dense retrieval has
no such limitation and already saturates recall@5, leaving RRF nothing to
add.

This is a property of the smoke set, not (necessarily) evidence that hybrid
retrieval doesn't help — a real novel corpus has many more candidate chunks
per query (hundreds, not 20) and includes exact-name and exact-quote lookups
where BM25's precision matters and dense's paraphrase tolerance is a
liability (surfacing a similar-sounding but wrong scene). **Action for
Sprint 8's ablation table (F6.3):** rebuild the smoke set with (a) some
queries that are near-verbatim quotes or character-name lookups where
lexical should win, and (b) a larger candidate pool, so recall@5 stops being
saturated and the comparison is actually discriminating.

## S2.10 — reranker, measured

Same smoke set, `BAAI/bge-reranker-v2-m3` (downloaded to the shared HF cache
during this sprint — it was not previously warmed).

**Quality:** MRR without rerank = 1.000, MRR with rerank = 1.000. No
measurable lift — expected, given S2.9's finding above: the baseline ranking
is already at ceiling on this corpus, so there is no headroom for a reranker
to recover.

**Latency:** 50 synthetic ~120-word candidates, CPU (`EMBEDDING_DEVICE=cpu`
in this worktree, per BRANCH.md §9 — no GPU is available here to avoid
contending with the shared vLLM), 8 runs after a warm-up call:

```
runs (ms): [495, 496, 496, 497, 499, 501, 512, 526]
p50 ≈ 499ms, worst-of-8 ≈ 526ms
```

Over the ≤400ms p95 budget. **BRANCH.md §9 is explicit that a timing number
taken from a worktree is not a valid production number** (this one doubly
so: CPU here, GPU in the real deploy), so this is not a claim that the
reranker "fails" the budget in production — it is a claim that it fails the
budget *on this hardware*, and that the honest thing to do until it is
re-measured on the integration host's GPU is leave it off.

**Decision:** `RERANKER_ENABLED` defaults to `False` (currently via
`getattr(settings, "reranker_enabled", False)` in `api/retrieval/rerank.py`,
pending SCR-2 — `api/config/settings.py` is orchestrator-owned as of this
sprint's freeze). Re-measure both quality (on a non-saturated smoke set) and
latency (on the integration host's GPU) before Sprint 8's ablation table
claims a number either way.

---

## What we learned (be2)

- `bge-reranker-v2-m3` was not in the shared model cache before this sprint;
  it is now (downloaded once, ~1.1GB, to `~/.cache/huggingface`). Future
  agents needing it will not pay this cost again. Worth `do1` adding it to
  `make warm-models` so it survives a cache eviction.
- The Sprint 1 prototype's embedding-model loader
  (`api/llm.py`'s `responder`) passed `cache_folder=settings.models_cache_dir`
  (`/models`, a container path) and `local_files_only=settings.models_offline`.
  Copying that pattern into `api/retrieval/repository.py` broke on a bare
  host, where the real cache is at `~/.cache/huggingface`, not `/models`.
  `api/pipeline/chunking.py`'s loader never passed `cache_folder` at all and
  works correctly on both host and container. Fixed to match. Worth a note
  wherever a new module loads a HF model: don't pass `cache_folder`/
  `local_files_only` explicitly unless you need to override the default
  resolution — `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` env vars already do
  the right thing.
- `api/config/settings.py` and `api/pyproject.toml` both being
  orchestrator-owned as of this freeze means any new feature flag or
  dependency needs an SCR mid-sprint even when it's a one-line default-off
  bool. Filed as SCR-2; non-blocking, but it's the second settings-shaped
  need in two sprints (SCR-3 last sprint was a dependency). Possibly worth
  the orchestrator pre-declaring a small "known likely flags" block per
  sprint's contract freeze based on the sprint plan's own acceptance
  criteria (`RERANKER_ENABLED` was explicitly named in `backend-2.md`).

## Action items (be2-relevant, proposed — orchestrator to confirm target sprint)

| # | Action | Owner | Target | Done? |
|---|---|---|---|---|
| A-2.1 | Land SCR-2 (`settings.reranker_enabled`, `settings.reranker_model_id`) | orchestrator | Sprint 3 freeze | No |
| A-2.2 | Rebuild the retrieval smoke set with lexically-anchored queries and a larger candidate pool so recall@5 isn't saturated | be2 | Sprint 8 (F6.3 ablation) | No |
| A-2.3 | Re-measure reranker latency on the integration host's GPU | be2 or do1 | Sprint 8 (F6.3 ablation) | No |
| A-2.4 | Add `bge-reranker-v2-m3` to `make warm-models` | do1 | Sprint 3 | No |

# Sprint 2 Retrospective

**Dates:** 2026-09-18 → 2026-09-22
**Goal:** Upload a real novel PDF and watch every stage complete, ending with
chapters, chunks, and embeddings in Postgres — each chunk carrying page
provenance you can click through to the rendered page.
**Outcome:** **Met**, with one open gap carried forward — the same shape as
Sprint 1: every branch's own tests were green, and the merge-train gate still
found four real bugs that no per-branch suite could see, plus one deeper,
unresolved corpus-generation problem (chapter detection) that the gate now
reports honestly instead of masking.

---

## 1. Delivered

| Story | Owner | Status | PRD ref | Notes |
|---|---|---|---|---|
| S2.1 | be1 | Done | F1.1 | Upload → MinIO, content-hash idempotency (`already_ingested`), chain dispatch. |
| S2.2 | be1 | Done | F1.1–1.3 | `pipeline.parse_and_chunk`, page-provenanced. |
| S2.3 | be1 | Done, accuracy number blocked | F1.4 | Regex + LLM-fallback chapter segmentation. The ≥95%-recall acceptance number cannot be produced — see "Chapter detection" below; not a be1 defect. |
| S2.4 | be1 | Done | F1.3 | `pipeline.embed_chunks`, batched, resumable. SCR-4 open (headings not threaded into the embedded text — retrieval-quality gap, not a crash). |
| S2.5 | be1 | Done | — | Retry, dead-letter, resume-from-last-good, `POST /reprocess`. Human-verified-chapter guard confirmed. |
| S2.6 | be1 | Done | — | Page render service, cached PNG + spans, PDF-point coordinate contract handed to fe1. |
| S2.7 | be2 | Done | — | `api/llm/` substrate — see be2's own section below. |
| S2.8 | be2 | Done, ahead of schedule | PRD §5.2 | Token-budget batcher, real tokenizer. |
| S2.9 | be2 | Done, measured | F4.1 | Hybrid retrieval — RRF ties dense's ceiling on this smoke set; see be2's section. |
| S2.10 | be2 | Done, default off | PRD §5.1 | Reranker behind a flag; over budget on worktree CPU, correctly not claimed as a production number. |
| S2.11 | fe1 | Done | F1.1 | Upload flow — drag-drop, progress, error recovery. |
| S2.12 | fe1 | Done | — | Live per-stage stepper, failure detail, retry button. |
| S2.13 | fe1 | Done | — | Chapters view + chunk inspector. SCR-6 open (no `chapter_id` filter on `GET /chunks` — client-side workaround ships). |
| S2.14 | fe1 | Done | — | Page viewer, PDF.js, span-highlight API surface ready for Sprint 6. |
| S2.15 | do1 | Done | — | MinIO storage helpers, signed URLs, 30-day lifecycle rule on page renders. Found + fixed a broken `traverse_test` DB along the way (`make test-api`). |
| S2.16 | do1 | Done | NFR-perf | Real five-novel PRD §7 corpus fetched, licensed, deterministically paginated. Gap found post-merge: see "Chapter detection" below. |
| S2.17 | do1 | Done | — | Cost accounting + Langfuse per-stage tracing scaffold; two-line wiring handed to be1 via HANDOFF. |
| S2.18 | do1 | Done, two bugs found running it | — | Fixture-novel ingestion gate + nightly real-corpus trend line. The gate itself needed two fixes before it could actually pass — see §4. |
| A-1.3 (carried) | do1 | Done | — | CI compose-boot gate for worker wiring; also fixed a probe/client-timeout race found while building it. |

**Merge-train result:** **Passed** on the cold `make test-integration` gate
(fresh volumes, `docker compose down -v`), after four fixes found running it —
none visible to any single branch's own test suite. See §4.

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
pending SCR-5 (renumbered from SCR-2 at the merge train — collided with do1's
own SCR-2) — `api/config/settings.py` is orchestrator-owned as of this
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
  bool. Filed as SCR-5; non-blocking, but it's the third settings/dependency-
  shaped need in two sprints (SCR-3 last sprint was a dependency, SCR-2 this
  sprint was do1's boto3). Possibly worth the orchestrator pre-declaring a
  small "known likely flags/deps" block per sprint's contract freeze based on
  the sprint plan's own acceptance criteria (`RERANKER_ENABLED` and `boto3`
  were both explicitly named in their sprint plans).

---

## be2's proposed action items (folded into §6 below)

| # | Action | Owner | Target |
|---|---|---|---|
| A-2.1 | Land SCR-5 (`settings.reranker_enabled`, `settings.reranker_model_id`) | orchestrator | Sprint 3 freeze |
| A-2.2 | Rebuild the retrieval smoke set with lexically-anchored queries and a larger candidate pool so recall@5 isn't saturated | be2 | Sprint 8 (F6.3 ablation) |
| A-2.3 | Re-measure reranker latency on the integration host's GPU | be2 or do1 | Sprint 8 (F6.3 ablation) |
| A-2.4 | Add `bge-reranker-v2-m3` to `make warm-models` | do1 | Sprint 3 |

---

## 2. Metrics

| Metric | Target | Actual | Δ |
|---|---|---|---|
| Stories completed | 18/18 + 1 carried | 18/18 + 1 carried | — |
| Merge-train order | fixed `do1 → be1 → be2 → fe1` (BRANCH.md §7) | **deviated**: `do1 → be2 → be1 → fe1` | see §4 |
| Merge-train conflicts | — | 8 shared-doc add/add (`HANDOFF.md` ×3, `SCR.md` ×3), 1 dependency-ordering (`api/llm`), 0 code-logic | see §4 |
| SCR numbering collisions | — | 3 separate agents (do1, be2, fe1) independently used "SCR-2" from the same base commit | see §4 |
| Bugs found running the cold merge-train gate | 0 | 4 fixed, 1 documented-not-fixed (chapter detection) | see §4 |
| Backend test suite (merged tree) | — | 241 passed, 1 skipped | |
| Frontend test suite | — | 128 passed | |
| Cold `make test-integration` | green before tag | green, on the 4th attempt | see §4 |

---

## 3. What went well

- **Every agent's own branch was fully green before the merge train started** —
  be1 (16 commits), be2 (5), do1 (9), fe1 (12), each independently verified
  (lint + full test suite through the `test` compose service, not host
  `pytest`) before rebasing. Zero code-logic conflicts across all four merges;
  every conflict was either a shared-doc append or the one real cross-agent
  dependency below.
- **A real cross-agent dependency was caught before it broke anything.** be1's
  S2.3 refactor onto `api.llm.structured_call` (be2's substrate) creates a
  dependency the sprint's generic merge order doesn't encode. Confirmed via
  `grep` that be2 has no reverse dependency on be1, swapped the order for this
  sprint only (`do1 → be2 → be1 → fe1`), and it was be2's own HANDOFF entry
  that had already flagged the exact risk ("be1 will not literally `import
  api.llm` until after their own merge") — the agent that would be broken by
  the wrong order wrote it down before the orchestrator found it.
- **The cold gate did its job again**, exactly per Sprint 1's A-1.1: every one
  of the four bugs below passed all 241 unit tests and both branch-level and
  post-merge test-suite runs; none were visible until the gate actually tore
  down and rebuilt the stack from nothing.
- **do1 finding a real bug in its own commit** (`traverse_test` never created
  for `make test-api`) and fixing it same-commit, rather than shipping it and
  letting the next person hit it, is the same discipline Sprint 1 praised in
  be1/fe1's testing.

## 4. What went wrong

- **The fixed merge-train order (`do1 → be1 → be2 → fe1`) was wrong for this
  sprint's actual dependency graph.** be1's branch could not even be
  `pytest`-collected in isolation once rebased onto a base that lacked
  be2's `api/llm/` package — its own worktree only worked because an
  untracked, gitignored local copy of `api/llm/` happened to still be on
  disk from before be1 stopped tracking it. Rebasing replayed that
  untracking commit's diff onto a base that legitimately had the real
  package, silently deleting it again. Caught before it merged; fixed by
  swapping be1 and be2's order and dropping the now-moot untracking commit
  from be1's history. **BRANCH.md §7's "dependency-driven, not political"
  framing needs a per-sprint check, not just a default**, since the default
  order is itself a specific sprint's dependency graph (Sprint 1's) frozen
  into a general rule.
- **Three agents independently filed "SCR-2" from the same base commit**
  (do1: boto3, be2: reranker flag, fe1: chunks chapter_id filter) — the same
  failure mode Sprint 1's retro already named ("a shared append-only doc from
  a common ancestor is always an add/add conflict"), but for *numbering*
  specifically, not just doc content. Renumbered do1→SCR-2 (kept, landed
  first in the merge train), be2→SCR-5, fe1→SCR-6, be1's own SCR-4 kept.
  Sprint 1's A-1.2 (seed `SCR.md`/`HANDOFF.md` as empty tracked files at the
  freeze) would not have prevented the *numbering* collision even if it had
  shipped — it only helps the doc-merge mechanics. **Still not done** (see
  §6, carried again).
- **The cold gate itself needed four fixes before it could pass** (detail in
  commit `a0f748e`):
  1. `AGENT_DATABASES`'s compose-file default and its postgres-init-script
     duplicate both drifted from `.env.example` — neither listed
     `traverse_test`, so a genuinely fresh Postgres volume never created it.
     Three copies of one list is one too many; nothing enforces they agree.
  2. Neither the embedding model's plain tokenizer nor the LLM's own
     tokenizer were warmed by `make warm-models` — only the
     `SentenceTransformer`-format embedding weights were, into a different
     cache root than `transformers.AutoTokenizer` reads from. Both
     `api/pipeline/chunking.py` and `api/llm/budget.py` hit the network for a
     model whose weights were already on disk.
  3. `scripts/test_integration_ingestion.py`'s poller trusted a single
     "failed" status read as terminal, catching a real ~1s window where
     Celery's `RETRY_POLICY` autoretry legitimately leaves the DB row FAILED
     between one attempt ending and the next starting.
  4. The same script required the book to reach `"ready"`, which — because
     `ingestion_chain()` chains all nine `StageName` stages regardless of
     what's landed, and an unbuilt one raises `NotImplementedError` on
     purpose — is structurally impossible before Sprint 8/9. It was asserting
     a condition that could never be true yet.
- **Chapter detection finds zero chapters on both the CI fixture and, by the
  same construction, do1's real seeded corpus.** Verified directly: Docling's
  layout model labels a heading from visual cues (font weight/size,
  mainly), and `scripts/seed_corpus.py::build_pdf()` renders the entire
  document — headings included — in one uniform, unstyled Courier. Every
  line comes back labelled plain `text`, never `SECTION_HEADER`/`TITLE`, so
  `DocumentChunker._segment_chapters` (which only looks at those two labels)
  has no candidates to run its regex against at all. Tried giving heading
  lines a larger font size, then a bold Courier variant (same character
  width, no re-wrap needed) — neither changed Docling's classification.
  **Not fixed.** This is not a be1 regression — the regex/LLM classification
  logic is correct against everything it's ever given a candidate for — it's
  a gap in how the corpus itself is built, and it blocks S2.3's own
  ≥95%-recall acceptance number as well as any Sprint 3/8 eval that assumes
  chapter boundaries exist in this corpus.

## 5. What we learned

- **A per-sprint dependency graph can invert the "generic" merge order.**
  Check actual imports (`grep -rn "from api\.<other-agent's-package>"`)
  across all four branches at freeze time or at merge-train time, not just
  once at Sprint 1.
- **A model's weights being on disk doesn't mean every code path that needs
  it is warmed.** `SentenceTransformer`, `transformers.AutoTokenizer`, and a
  bare `snapshot_download` each resolve their own cache root differently;
  "the model is cached" is not one fact, it's one fact per loader.
- **A retry policy with backoff makes a stage's *current* state a bad proxy
  for whether the book is *actually* failing.** Any future poller against
  `derive_book_status` needs the same debounce `test_integration_ingestion.py`
  now has, or it will flake the same way.
- **A synthetic or re-rendered PDF is only as good as its typography.**
  Deterministic pagination (do1's real, valuable design constraint for
  page-exact citation) and typographically-detectable structure (what
  Docling's heading classifier needs) are in tension, and nobody had
  connected the two until a real end-to-end run exposed it. Worth exploring
  *before* Sprint 3 leans on this corpus for anything chapter-shaped.

---

## 6. Action items

| # | Action | Owner | Target | Done? |
|---|---|---|---|---|
| A-2.1 | Land SCR-5 (`settings.reranker_enabled`, `settings.reranker_model_id`) | orchestrator | Sprint 3 freeze | No |
| A-2.2 | Rebuild the retrieval smoke set with lexically-anchored queries and a larger candidate pool so recall@5 isn't saturated | be2 | Sprint 8 (F6.3 ablation) | No |
| A-2.3 | Re-measure reranker latency on the integration host's GPU | be2 or do1 | Sprint 8 (F6.3 ablation) | No |
| A-2.4 | Add `bge-reranker-v2-m3` to `make warm-models` | do1 | Sprint 3 | No |
| A-2.5 | File a real SCR for the chapter-detection/corpus-typography gap (§4) and design a fix — give headings genuine visual distinction Docling's layout model responds to, without changing the pinned pagination constants | do1, with be1 input | Before Sprint 3's chapter-truth eval work | No |
| A-2.6 | Land SCR-2 (`boto3` in `api/pyproject.toml`, drop the Dockerfile/CI stopgap) | orchestrator | Sprint 3 freeze | No |
| A-2.7 | Land SCR-4 (`ChunkPayload.headings`, threaded into embedded text) | orchestrator + be1 | Sprint 3 freeze | No |
| A-2.8 | Land SCR-6 (`chapter_id` filter on `GET /books/{id}/chunks`) | orchestrator + be1 | Sprint 3 freeze | No |
| A-2.9 | Check the real per-sprint dependency graph (not just the Sprint 1 default) before fixing the merge-train order at each freeze | orchestrator | Every sprint, starting now | Adopted this retro |

**Carried from Sprint 1:**

| # | Action | Status |
|---|---|---|
| A-1.2 | Seed `HANDOFF.md`/`SCR.md`/`STANDUP.md` as empty tracked files at the freeze | **Still not done** — same add/add conflicts recurred this sprint, plus a numbering collision A-1.2 wouldn't have prevented anyway (see §4) |
| A-1.4 | Reconcile NFR-deploy's "<5 min" with a literal cold-volume demo | Not addressed this sprint |
| A-1.5 | Document per-agent vs. container-default vs. test database distinction | **Done** this sprint (`.agents/skills/codebase-memory/infra-topology.md`), prompted by the `traverse_test` bug in §4 |
| A-1.6 | Standing rule for post-merge integration bugs: orchestrator fixes directly vs. a fix-forward agent turn | Still undecided; orchestrator continued fixing directly this sprint (commit `a0f748e`), same as Sprint 1 |
| A-1.7 | Resolve the accessibility-gating contradiction (`PRODUCT.md` vs. `plans/sprint-9/frontend-1.md`) | Not addressed this sprint |

---

## 7. PRD amendments

None. Every finding this sprint was implementation/process, not a wrong
product assumption — including the chapter-detection gap, which is a
corpus-construction defect, not evidence that F1.4's chapter-detection
requirement itself is wrong.

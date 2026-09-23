# Sprint 3 — Standup

## do1 — 2026-09-22

**Landed:**
- Day 1/2 priority: fixed the chapter-detection corpus gap (SCR-1) — a
  chapter heading now renders 16pt Courier-Bold instead of matching body
  text, which crosses Docling's classification threshold; verified directly
  against the installed layout model on both a synthetic probe and the real
  regenerated corpus (`CHAPTER III.`/`CHAPTER IV.` → `section_header`). Page
  counts unchanged across all five books — only `pdf_sha256` moved.
- S3.13: gold rosters for Pride and Prejudice (25 characters) and Wuthering
  Heights (14 characters, two Catherines correctly kept apart with
  `collision_group`), JSON-Schema-validated and pinned to the regenerated
  corpus's checksums. `scripts/label_roster.py` terminal review tool built
  and unit-tested (confirm/edit/split/reject loop), reusable for Sprint 8.
- S3.14: `eval/metrics.py` — roster P/R/F1, a real B³ implementation
  verified against a hand-computed toy example (5/9 exactly, by hand and in
  a committed test), tier accuracy, rejection precision, cascade-stage
  contribution. Wired into a new `GET /ops/extraction-quality` endpoint
  reading the real `Character`/`CharacterAppearance`/`CharacterMention`/
  `RejectedCandidate` tables. `eval/runners/extraction.py` renders the
  PR-comment markdown table with a baseline delta.
  `.github/workflows/extraction-quality.yml` wired for PRs touching
  `api/extraction/**` (one-novel reduced set) — not yet run for real, no
  `api/extraction/**` exists on any branch yet to trigger it.
- S3.15: `GET /ops/extraction-cost` (tokens, dual-rate USD, wall clock/100
  pages). `api/ops/vllm_metrics.py` scrapes vLLM's own Prometheus endpoint —
  `GET /ops/metrics`'s existing (frozen, previously-always-`None`)
  `prefix_cache_hit_rate` field is now live when running local inference.
  `scripts/nightly_corpus_ingestion.py` extended to post extraction
  quality/cost for gold-labelled books on the existing nightly run.
- Filed SCR-1 (informational fix record), SCR-2 (MetricsOut/StageCost field
  request, non-blocking), SCR-3 (a be1-owned frozen-path-count test needs a
  bump past 34 — do1's two new routes make it 36; be2's routes will hit the
  same assertion independently this sprint).

**Next:** available for be1/be2 questions on the gold-set schema or the new
ops endpoints; otherwise S3.13-S3.15 are complete per devops-1.md's DoD.

**Blocked:** nothing. One known, documented, non-blocking test failure on
this branch (SCR-3, see HANDOFF.md) — not a bug in do1's own code, a
cross-agent frozen-count collision that be2 will independently hit this
sprint regardless of what happens with this branch.
## be2

**Landed:** S3.6 (character read APIs — `list_mentions` and `get_character`
implemented for real against Postgres, paginated, `limit_book_order`/
`limit_chapter`-aware on every character endpoint including the mentions and
per-chapter histogram, not just the roster; fixed a real bug found along the
way — `list_characters`' reading-position filter excluded every character
whose first book had a `NULL series_order` instead of treating it as "no
restriction", inconsistent with the pattern `retrieval/repository.py`
already established for the same nullable column), S3.7 (`merge`/`split`,
transactional, mention re-pointing, appearance consolidation and derived-field
recomputation shared between both directions so a merge followed by a split
restores the original partition), S3.8 (`cluster_contexts` + a real measured
precision/recall curve from actual *Pride and Prejudice* text and the real
BGE-M3 model — see HANDOFF.md, threshold set to 0.65, precision-biased on
purpose), S3.9 (relation extraction spike run against a live vLLM with the
real Qwen3-8B-AWQ model — full findings in HANDOFF.md, delivered before Day
4). All on `ai/be2/sprint-3-characters`; nothing merged to `ai-master` yet.

**Next:** Nothing left in `backend-2.md`'s scope for Sprint 3. Available to
help unblock be1's S3.1-S3.5 landing against the read APIs and the
similarity service, or to start early on S4 prep if the orchestrator wants
that.

**Blocked:** Not blocked. Filed SCR-6 (non-blocking) for
`settings.mention_similarity_threshold` — shipped S3.8 with a `getattr`
default in the meantime (same pattern as Sprint 2's SCR-5), so nothing is
waiting on it. Flagged a real infra bug to do1 in HANDOFF.md: the `vllm`
compose service's cache-path layout disagrees with `api`/`celery-worker`'s,
so a cold `docker compose --profile gpu up` re-downloads the whole model
instead of finding the warmed cache — cost me about 10 minutes during the
S3.9 spike, not blocking but worth a one-line fix before Sprint 4's demo day.

**Correction to an earlier version of this note:** I initially flagged
`test_the_openapi_document_still_lists_every_frozen_path` as a pre-existing
36-vs-34 path-count mismatch unrelated to this branch. That was wrong, and
the cause was exactly the shared-image trap `docker compose --profile test
run --rm test` without an immediately preceding `build test` can fall into
— `traverse-api-test:dev` is one tag shared by all four worktrees, and a
`run` a few minutes after a `build` (with another worktree's agent doing its
own build in between) silently tests someone else's tree. Rebuilding
immediately before the final run reproduced the correct, frozen count (34)
and the full suite is green:
`docker compose --profile test build test && docker compose --profile test
run --rm --no-deps test pytest api/tests -q` → **261 passed, 1 skipped, 0
failed.** Lesson for next sprint: never trust a `test` run that isn't
preceded by its own `build` in the same breath.
## be1

**Landed:** S3.1 (`pipeline.extract_characters` — batched pass-1 discovery via
`structured_call`/`plan_batches`), S3.2 (non-character rejection with stored
reasons, including the ambiguous house-vs-family case), S3.3 (5-stage alias
cascade — normalise → honorific/name-order → nickname → embedding →
LLM-adjudicated residue, each stage recording `resolution_method`), S3.4
(name-collision guard — distinct-qualifier / generational-marker /
kinship-phrase / lifespan-disjointness signals, blocking a merge and queuing
a `merge_characters` review row instead), S3.5 (character/appearance/mention
persistence, both tiering methods behind `TIERING_METHOD`, page-cited
attribute extraction). All on `ai/be1/sprint-3-characters`.
`api/extraction/honorifics.yaml` and `nicknames.yaml` are the data-driven
tables the plan asked for instead of inline regex. 48 new tests in
`api/tests/extraction/`, 3 in `api/tests/pipeline/test_extraction_tasks.py`
covering both Celery task bodies end-to-end against real Postgres; full
targeted suite (`api/tests/pipeline api/tests/extraction api/tests/llm`) green
at 200 passed. `test_wuthering_heights_two_catherines` and
`test_no_false_splits` committed as permanent regression tests.

**Next:** Nothing left in `backend-1.md`'s scope for this sprint. Available to
help unblock be2's S3.8 (I'm depending on `api.graph.similarity.cluster_contexts`
for cascade stage 4 — currently no-ops gracefully without it, see HANDOFF) or
pick up early S4 prep if the orchestrator wants it.

**Blocked:** Not blocked. Filed SCR-1 (non-blocking) for a `TIERING_METHOD`
settings key — reading `os.environ` directly in the meantime, identical
behaviour. The real P/R/F1 / B³ / tier-accuracy numbers against labelled
novels need do1's S3.13 harness and a real seeded corpus, neither of which
exist in this worktree — flagged in HANDOFF as a Day-5 integration item
rather than claimed from here, same pattern as Sprint 2's chapter-detection
accuracy note.

## be1 — post-merge train integration fix, 2026-09-23

The orchestrator caught a real bug during the merge train:
`api/extraction/similarity.py::context_similarity` assumed a pairwise
`cluster_contexts(text_a, text_b) -> float` shape. be2's actual, spec-compliant
S3.8 API (`api/graph/similarity.py`) is a **batch** clusterer —
`cluster_contexts(mentions: list[MentionContext], *, threshold: float) ->
list[list[UUID]]` — exactly what `backend-2.md` specified. My adapter's
`try/except ImportError` guard meant this mismatch was invisible for the
entire sprint: `api.graph.similarity` didn't exist in my worktree, so every
call to it hit the `ImportError` branch and returned `None` before the wrong
call signature ever executed. **48/48 extraction tests green in isolation
proved nothing about this path** — they proved the *degraded* path worked,
which was never the code that ships. The bug only surfaced once be2's real
module was actually importable, i.e. at integration.

Fixed by having the adapter construct two `MentionContext` objects and call
the real batch API with exactly two items, reading "clustered into one group"
as the pairwise signal `aliases.py`'s cascade wants
(`len(cluster_contexts([a, b], threshold=...)) == 1`). No change needed to
`aliases.py` itself — the `decide(a, b) -> ResolutionMethod | None` shape it
already used was sound; only the adapter underneath it was wrong.

One test needed a real fix, not a weakening: `test_aliases.py::TestLLMStage
::test_merges_a_shared_surname_residue_pair` had implicitly relied on stage 4
being a permanent no-op (true only in an isolated worktree) to guarantee its
"Elizabeth Bennet"/"Miss Bennet" pair reached the LLM stage it's named for.
With the real embedding service wired up, that pair now legitimately clusters
at the cheaper stage 4 instead — correct cascade behaviour, but it meant the
test was no longer isolating what it claimed to test. Fixed by stubbing
`similarity.context_similarity` to return `None` for that one test, forcing
the residue through to stage 5 as originally intended — the assertion itself
(`resolution_method == LLM`) is unchanged.

**Retro-worthy:** a mocked-dependency adapter with a graceful degrade path
(`try/except ImportError`) can pass 100% of its own tests while calling a
contract that was never real. The `except ImportError` branch is exactly the
place a signature mismatch hides — worth a standing question at future
freezes: for any cross-agent adapter with a "not landed yet" fallback, does
at least one test exercise the *real* signature (a `Protocol`/fake with the
actual parameter list), not just the degrade path? Filed nowhere formally
this sprint; raising it here so it reaches the retro.

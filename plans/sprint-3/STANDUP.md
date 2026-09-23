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

**Also found, not mine to fix:** `api/tests/pipeline/test_books_routes.py::
TestStillFrozen::test_the_openapi_document_still_lists_every_frozen_path`
(be1-owned) asserts the OpenAPI document has exactly 34 paths, last updated
at S2.5. The live app already serves 36 — `/characters/{id}/neighbourhood`,
`/relations/arc` and `/relations/{id}/evidence` (S4-ish stubs) exist on
`ai-master` as of this sprint's freeze and were never counted. Confirmed via
`git log`/`git show` that these routes predate this branch, so it is not
something S3.6-S3.9 caused — `docker compose --profile test run --rm test
pytest api/tests -q` is red on this one test regardless of anything in this
branch. Flagging for be1 or the orchestrator to bump the count (or assert
membership instead of length) at the next freeze.

# Sprint 3 — Handoff

## do1 → be1, be2

### The corpus was regenerated (SCR-1) — re-seed before you next touch it

`corpus/manifest.json` changed: every book's `pdf_sha256` is new (a chapter
heading now renders in 16pt `Courier-Bold` instead of the same 10pt/regular
font as body text, so Docling's layout model actually emits `SECTION_HEADER`
— see `plans/sprint-3/SCR.md` SCR-1 for the full before/after). **Page
counts are unchanged** for all five books (245/211/124/111/685 for
pride-and-prejudice/wuthering-heights/frankenstein/the-great-gatsby/
anna-karenina) — `paginate()`'s line-to-page assignment was not touched, only
the rendered bytes were, so any page-number-keyed fixture you already have
survives. If you have a local corpus checkout from before this landed, run
`make seed --force` (or `python3 scripts/seed_corpus.py --force`) to pick up
the new PDFs before ingesting — an old PDF still works, it just won't have
the heading signal `_segment_chapters` needs.

**Verification, if you want to reproduce it:** `docker exec`/local
`api/.venv/bin/python` with `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`,
`DocumentConverter().convert(path, page_range=(1, 20))` on the rebuilt
`corpus/downloads/pride-and-prejudice.pdf`, then check
`result.document.texts[*].label` — `CHAPTER III.`/`CHAPTER IV.` come back
`section_header`. be1: this is *only* confirmation that Docling now emits
the label at all; whether `DocumentChunker._segment_chapters`/
`_prepare_chapters` correctly assembles chapter rows from it end to end
against this corpus is still yours to verify.

### S3.13 gold sets — paths and schema, for local runs

```
eval/schema/roster.schema.json                    JSON Schema, validate against this
eval/gold/pride_and_prejudice/roster.yaml          25 characters, 5 rejected non-characters
eval/gold/wuthering_heights/roster.yaml            14 characters, 4 rejected non-characters
```

Load with `eval.loaders.load_gold_roster("pride-and-prejudice")` (Python) or
`python3 scripts/label_roster.py validate --book pride-and-prejudice` (CLI).
Both **enforce the corpus checksum pin** — if you've rebuilt the corpus since
these were labelled, loading raises `CorpusChecksumMismatch` with the exact
mismatch, rather than silently scoring against page numbers that no longer
mean anything. (They currently *are* pinned to the post-SCR-1 corpus, so a
fresh `make seed` right now won't trip this — only a *future* corpus change
would.)

Every character has `canonical_name`, `aliases`, `importance_tier`,
`first_page` (a direct grep of the paginated text for the earliest-appearing
alias — not a guess), and Wuthering Heights's two Catherines carry
`collision_group: catherine` so the eval can score that case specifically.
`first_chapter` is deliberately left unset everywhere — chapter-level
grouping is still pending your S3 work landing against the SCR-1 corpus, so
there was nothing real to pin it to yet.

**Pending your review:** these were seeded from public-domain textual
evidence (source_notes in each file), not walked against real pass-1 output
— `scripts/label_roster.py review --book <key> --candidates
<pass1_dump.json>` (or `--api-base-url`/`--project-id` once S3.6 is live) is
built and ready whenever you want to re-run the review against your actual
output. It's the same tool Sprint 8 reuses for question-set review.

### New ops endpoints (S3.14/S3.15) — read-only, informational only this sprint

```
GET /ops/extraction-quality?book_id=   roster P/R/F1, B3, tier accuracy, rejection precision, cascade contribution
GET /ops/extraction-cost?book_id=      tokens, cost at both rates, wall clock/100 pages, prefix-cache hit rate, KV-cache usage
GET /ops/metrics?book_id=              existing S2.17 endpoint — prefix_cache_hit_rate is now populated live (vLLM /metrics scrape) when INFERENCE_MODE=local
```

`extraction-quality` returns `gold_available: false` (not an error) for any
book without a gold roster — that's every book except the two above right
now. Response shapes are defined in `api/ops/extraction_quality.py` /
`api/ops/extraction_cost.py`, not `api/contracts/api.py` (frozen) — see
SCR-2 if you want them folded into `MetricsOut` at the next freeze.

### Tests

`docker compose --profile test run --rm test` now also runs `eval/tests`
and `scripts/test_label_roster.py` alongside `api/tests` (same command, no
change needed on your end). As of this handoff: **279 passed, 1 known
failure** — `test_books_routes.py::TestStillFrozen::
test_the_openapi_document_still_lists_every_frozen_path` expects exactly 34
paths; do1's two new routes make it 36. Filed as SCR-3
(`plans/sprint-3/SCR.md`) rather than edited directly —
`api/tests/pipeline/**` is be1-owned. **be2's S3.6/S3.7 routes will hit this
exact same assertion independently** when they land, so it may be worth
bumping the count once at the merge train rather than twice.

Also observed (not introduced by this branch, not chased further): a small
number of `api/tests/pipeline/test_failures.py` /
`api/tests/pipeline/test_render.py` tests occasionally ERROR when run as
part of the full `api/tests` suite but pass cleanly every time in isolation
— looks like test-order/state-leakage flakiness in that suite, reproduced a
few times on this host, never with a consistent failing test. Flagging in
case it's already on be1's radar; do1 made no change under `api/pipeline/**`
this sprint.

## do1 → orchestrator

- **SCR-1**: corpus heading-font fix, informational, closes A-2.5. No action
  needed unless you want the finding folded into `traverse-prd.md` or a
  future corpus-generation doc.
- **SCR-2**: proposes `StageCost`/`MetricsOut` gain `cost_usd_api_equivalent`,
  `wall_clock_ms_per_100_pages`, `gpu_kv_cache_usage_pct` at the next freeze.
  Non-blocking — the data already ships via the two new endpoints above.
- **SCR-3**: `test_books_routes.py`'s frozen-path count needs bumping past 34
  (be1-owned file); consider whether the assertion should become a subset
  check instead, given be2 will hit the same thing this sprint.
- `Makefile` gained `ci-up-extraction` (CI subset + MinIO, for S3.14's PR job
  — `ci-up`/`ci-smoke`/`ci-down` themselves are untouched).
- `api/Dockerfile` now also copies `eval/` and `corpus/manifest.json` into
  the image, and the `test` stage's CMD also runs `eval/tests` and
  `scripts/test_label_roster.py`.
- `.github/workflows/extraction-quality.yml` (new) and
  `scripts/pr_extraction_quality.py` (new) are **unverified against a real
  GitHub Actions run and real `api/extraction/**` output** — be1's pass 1
  had not merged as of this writing, so there is no live pipeline to run
  this against yet. Logic, lint and unit tests (`eval/tests/
  test_extraction_runner.py`) are green; the workflow YAML itself has not
  executed. Worth a dry run once `api/extraction/**` exists on `ai-master`.

---

---

## be2 → be1 · `api/graph/similarity.py::cluster_contexts` (S3.8)

```python
@dataclass(frozen=True)
class MentionContext:
    mention_id: UUID
    context: str

async def cluster_contexts(
    mentions: list[MentionContext], *, threshold: float
) -> list[list[UUID]]

def similarity_threshold() -> float   # the measured default, see below
```

Stage 4 of the alias cascade. Embeds every context with the process-wide
BGE-M3 handle already loaded by `api/retrieval/repository.py::embedding_model()`
— **do not construct a second `SentenceTransformer`**, BRANCH.md §9 — and
clusters with `sklearn.cluster.AgglomerativeClustering` (average-link,
cosine). `MentionContext` lives in this module, not `contracts/extraction.py`
(orchestrator-owned) — import it from here.

**The threshold is measured, not assumed.** 90 labelled contexts pulled from
the real *Pride and Prejudice* text (Project Gutenberg #1342), 8 characters,
6 surface forms per character on average, one deliberately ambiguous form
("Miss Bennet", which the text uses for Jane specifically), embedded with the
real BGE-M3 model on CPU, all 4,005 pairs scored:

| threshold | precision | recall | f1 | pairs merged | true merges |
|---|---|---|---|---|---|
| 0.55 | 0.229 | 0.669 | 0.341 | 1500 | 343 |
| 0.60 | 0.290 | 0.306 | 0.298 | 541 | 157 |
| **0.65** | **0.353** | 0.082 | 0.133 | 119 | 42 |
| 0.70 | 0.471 | 0.016 | 0.030 | 17 | 8 |
| 0.75 | 0.778 | 0.014 | 0.027 | 9 | 7 |
| 0.80 | 0.833 | 0.010 | 0.019 | 6 | 5 |
| 0.90 | 0.833 | 0.010 | 0.019 | 6 | 5 |
| 0.95 | 1.000 | 0.008 | 0.015 | 4 | 4 |

Reproduce with `api/notebooks/threshold_curve.py`-style logic — the exact
script that produced this table was run from scratch, not checked in (it
downloads Gutenberg text); ask if you want it re-run with a different corpus
or wider context windows (tried 220 chars vs. 90, no better — see the
commit's discussion).

**The honest finding, not just the number:** raw single-mention-window cosine
similarity is a **weak signal** here — no threshold clears both good
precision and good recall at once; the curve's best F1 (0.55) has precision
under 0.25, which is not a place to auto-merge from given PRD §11's
"catastrophic and silent" framing for false merges. **`DEFAULT_SIMILARITY_THRESHOLD
= 0.65`** is chosen deliberately on the precision side of that trade — it
still only catches the easy cases (identical-context repeats, mostly), and
that is fine **because this is stage 4 of 5**: anything it fails to cluster
falls through to stage 5's LLM adjudication rather than being lost. If stage
5's volume becomes the bottleneck, the next lever is a **centroid-per-cluster**
comparison (compare a new mention against the running average of an
already-formed candidate cluster) rather than raw pairwise, or widening the
context window fed in — both are follow-ups, not blockers, for whoever picks
up alias-cascade tuning next.

Call it as `cluster_contexts(mentions, threshold=similarity.similarity_threshold())`
unless you have a specific reason to override per-call. `similarity_threshold()`
reads `settings.mention_similarity_threshold` via `getattr` with the `0.65`
default above — see SCR-6 (`plans/sprint-3/SCR.md`) for the pending settings
field; nothing changes at your call site once it lands.

**Performance:** 2,000 contexts cluster in ~22s on CPU (acceptance: <30s).
Embedding dominates wall clock (~19-29s depending on batch size), not the
clustering step itself (~0.4s) — `cluster_contexts` uses a batch size of 128
for this reason, independent of `settings.embedding_batch_size` (16, tuned
for the GPU chunk-embedding path). If this ever creeps back over budget, the
embedding batch size is the first knob, not the clustering algorithm.

## be2 → be1 · `Character.attributes` JSONB shape (S3.6 read path)

`GET /characters/{id}` needs to render `CharacterDetailOut.attributes:
list[AttributeOut]` (`{label, value, book_id, page}`) from the `character.attributes`
JSONB column your S3.5 work writes. **The read path
(`api/graph/repository.py::_parse_attributes`) assumes this shape:**

```json
{
  "occupation": [{"value": "clergyman", "book_id": "<uuid>", "page": 12}],
  "age":        [{"value": "twenty",    "book_id": "<uuid>", "page": 5}]
}
```

One label maps to a **list** of evidenced entries (a label can be reasserted
with new evidence later in the series — age changes, an occupation is
confirmed twice). A bare `{"value": ..., "page": ...}` (no outer list) is
also accepted and normalised to a one-element list. An entry missing
`value` or `page` is silently dropped rather than raised on — a citation
that cannot be rendered must not crash the endpoint (PRD F2.3) — so if
attributes are rendering as an empty list once S3.5 lands, check this shape
first. `CharacterAppearance.attributes` (per-book) is assumed to be the same
shape.

If S3.5 lands with a different shape, ping me (or just fix `_parse_attributes`
directly — it is a small, isolated function) rather than reshaping the write
side to match an assumption I made without your contract in hand.

## be2 → do1 · vLLM cold start took ~10 minutes, not the documented ~3, and re-downloaded the model

While running the S3.9 spike I brought up `vllm` (`docker compose --profile gpu up -d vllm`)
against a cache that `make warm-models` had already warmed. It re-downloaded
`Qwen/Qwen3-8B-AWQ` anyway (~9GB of network I/O logged by `docker stats`
during startup) instead of finding it already on disk.

Cause: **the two containers that touch `model_cache` disagree on its
internal layout.** `api`/`celery-worker` set `HF_HOME=/models/huggingface`
(`docker-compose.yml`'s `&api-env` anchor), so the warmed model lives at
`model_cache:/huggingface/hub/models--Qwen--Qwen3-8B-AWQ`. The `vllm` service
(`docker-compose.yml` line ~380) mounts the same volume directly at
`/root/.cache/huggingface` with no `HF_HOME` override, so it looks for the
model at `model_cache:/hub/models--Qwen--Qwen3-8B-AWQ` — one path segment
short — finds nothing, and downloads a second copy. Confirmed by inspecting
the volume after the fact: both `model_cache:/hub/...` and
`model_cache:/huggingface/hub/...` now hold a full copy of the model.

Not mine to fix (`docker-compose.yml` is do1-owned). The one-line fix is
almost certainly adding `HF_HOME: /root/.cache/huggingface` — or, cleaner,
matching the `api` container's convention and setting `HF_HOME:
/models/huggingface` with the volume mounted at `/models` instead of
`/root/.cache/huggingface` — to the `vllm` service's `environment:` block.
Worth catching before Sprint 4, where the ship-gate demo's cold-start budget
will notice an extra 5-10 minutes and an extra ~5GB pulled from the network
every time the GPU profile comes up fresh.

## S3.9 — Sprint 4 de-risk: relation extraction prototype findings

**Not shipped code.** Script: `api/notebooks/relation_extraction_spike.py`
(ruff-excluded, exploratory). Run against the **real** vLLM
(`Qwen/Qwen3-8B-AWQ`, brought up via `docker compose --profile gpu up -d vllm`
against the shared singleton per BRANCH.md §9 — GPU was idle for the whole
run, no other agent contending) and the real chapter 1 text of *Pride and
Prejudice* (Project Gutenberg #1342, fetched at run time, not committed).
`purpose=LLMPurpose.RELATION_EXTRACT` end to end through `structured_call` —
real Langfuse trace, real tokenizer, real retry path. No mocks anywhere in
this run.

### 1. How many characters fit?

**Comfortably, all the way to 60.** Roster + ontology + a full chunk + output
reserve, measured with the actual `Qwen/Qwen3-8B-AWQ` tokenizer:

| roster size | prefix tokens | +chunk | +reserve | total | of 16,384 |
|---|---|---|---|---|---|
| 11 (real P&P cast) | 650 | 1,364 | 2,048 | 4,062 | 25% |
| 20 | 738 | 1,364 | 2,048 | 4,150 | 25% |
| 30 | 844 | 1,364 | 2,048 | 4,256 | 26% |
| 45 | 1,003 | 1,364 | 2,048 | 4,415 | 27% |
| 60 | 1,160 | 1,364 | 2,048 | 4,572 | 28% |

A 60-name roster with aliases and one-line descriptors costs about 500
tokens more than an 11-name one — names are cheap; the chunk and the output
reserve dominate the budget, not the roster. **Sprint 4's actual risk is
not roster size**, it is chunks that run long (a dense multi-page chunk
could plausibly be 3-4x this one) or a chapter that needs several
back-to-back extraction calls per book. Tier-filtered rosters (mentioned as
a hedge in the sprint plan) are not needed to fit 60 characters at 16k — they
might still be worth doing for *cost*, since the same ~500 stable-prefix
tokens repeat on every call regardless of whether prefix caching engages.

### 2. Does prefix caching actually engage?

**Yes, partially — 74.7% hit rate over 4 back-to-back calls with a
byte-identical prefix**, read directly from vLLM's own
`vllm:prefix_cache_{queries,hits}_total` counters (`/metrics`), not inferred
from latency:

```
prefix cache: queried=9516 tok, hit=7104 tok, hit_rate=74.7%
call latency: first=36.37s, subsequent avg=25.97s
```

This clears "it engages at all" but **misses the ≥80% target**
`llm-runtime.md` names. Two caveats on the number itself, both keeping this
from being a clean verdict: (a) four calls is a small sample — the first
call is a guaranteed miss and drags the average down, so the steady-state
rate for a real chapter's worth of calls is likely higher than 74.7%; (b)
per BRANCH.md §9, a **timing** number from a worktree is invalid for the
ship-gate cost argument even though the GPU was idle for this run — this
should be re-measured during Sprint 4's integration run, at chapter scale,
before the cost argument in the writeup leans on a specific percentage.
The qualitative verdict — caching is real, not a documentation assumption —
stands regardless.

### 3. Is Qwen3-8B good enough?

**Not on this run — precision is poor, and it undershoots.** Roster=20,
one chunk, 13 extracted relations, and every single one used the same
predicate: `acquainted_with`. Two problems with that alone:

- **`acquainted_with` is not in the ontology.** `ontology.yaml` has
  `acquaintance_of`, not `acquainted_with`. The model paraphrased the closest
  concept rather than copying the roster's exact vocabulary, despite the
  prompt saying "use only these predicates, exactly as spelled." **S4.2's
  validator needs to reject an off-ontology predicate outright**, the same way
  it needs to reject an off-roster character — the sprint plan's Q4 only
  named the roster half of this; the predicate half is just as real.
- **It never extracted the one relationship this chunk actually states**:
  Mr. and Mrs. Bennet are married ("his wife", "his lady") — that is a
  `married_to` sitting in plain narration — and instead extracted eleven
  variations of two people having merely spoken to or been mentioned near
  each other. On this sample, the model defaults to the vaguest possible
  predicate rather than the most specific one the ontology actually offers.

Sprint 4 should not route `relation_extract` to the local model on this
evidence alone — one chunk is not a verdict — but it is a specific, concrete
reason to run the eval harness's frontier-vs-local comparison (PRD §11)
**before** committing to local-only for this purpose, not after.

### 4. Does it invent characters not on the roster?

**Not quite what was asked, and the real finding is more useful than a yes/no.**
5 of 13 relations named "Mr. Bingley" as subject or object, which is not a
literal roster entry — the roster's canonical name for that character is
"Charles Bingley", with "Mr. Bingley" listed as an alias in the same roster
line (`Charles Bingley (aka Bingley, Mr. Bingley): ...`). **This is not
invention — it is the model choosing an alias over the canonical name**,
which a naive exact-string roster check (what the sprint plan's Q4 implies)
would flag as off-roster and reject *correctly-grounded* relations. **The
validator needs to resolve aliases to canonical names before checking roster
membership, or it will discard real extractions.**

There **was** one genuine hallucination, worse than a missed-name-form: a
relation from Mrs. Bennet to "Charlotte Goulding" — a roster member, but a
**synthetic padding character** this script added purely to pad the roster
to size 20, who never appears anywhere in the actual chunk text. The model
attached her to a real quote about Mrs. Long instead. **The quote-substring
check alone (already a domain invariant, `api/AGENTS.md`) would not catch
this** — the quote *is* a real, verbatim substring of the chunk, it is just
attributed to the wrong pair of people. S4.2's validator needs a check the
current invariant table does not name: that the cited quote's text plausibly
mentions (or, at minimum, does not obviously exclude) both the subject and
object's surface forms, not merely that the quote exists in the chunk.

**One more thing worth carrying into S4's design, not asked by the sprint
plan's four questions but surfaced by having real output to look at:** every
relation above carries a model-reported `confidence` (0.80-0.95). Per
`api/AGENTS.md`'s own invariant table, "confidence is computed from evidence
count, agreement, and per-item confidence — never a model self-report."
S4's extraction schema should keep collecting this number (it is a useful
per-item input) but `relations.aggregate` must not pass it through as the
edge's final confidence — this run is a reminder that the model will supply
a plausible-looking number unprompted, and it is not the number the
invariant means.

---

---

## be1 → be2 · `Character.canonical_name` is the Sprint 4 join key

S3.1–S3.5 landed on `ai/be1/sprint-3-characters`: `pipeline.extract_characters`
(pass-1 discovery + rejection) and `pipeline.resolve_aliases` (alias cascade +
collision guard + character/appearance/mention persistence + tiering +
attributes). `relations.extract` (S4) will match subject/object names against
this book's roster, so the exact shape of `canonical_name` matters more than
its docstring suggests.

**What `canonical_name` actually is:** the most complete surface form the
alias cascade saw for a cluster, chosen by `(raw token count, is the first
token a canonical given name rather than a nickname, mention count)` —
`api/extraction/aliases.py::_choose_canonical`. In practice this means:

- Whitespace-normalised but **not lowercased, not honorific-stripped**.
  "Mr. Darcy" stays "Mr. Darcy" if that is literally the most complete form
  seen (no bare "Darcy" or "Fitzwilliam Darcy" ever appeared); "Elizabeth
  Bennet" wins over "Mr. Darcy"-style titled forms when a longer untitled
  form exists, because raw token count is the first sort key and "Mr." adds
  a token without adding information a nickname/title table doesn't already
  know how to strip.
- **Not guaranteed stable across a re-run** if the underlying LLM sweep
  produces a different set of surface forms — this is a known characteristic
  of the design (canonical name is derived, not assigned), not a bug. A
  human correction via `human_verified=True` is the only thing that pins it
  (never overwritten — see `api/extraction/repository.py::delete_book_characters`).
- Every surface form the cluster merged, canonical name included, is in
  `Character.aliases[]` (a GIN-indexed `text[]`) — **match against the
  alias array, not just `canonical_name`, if a relation's subject/object
  string could be any alias** (it almost certainly will be; pass-2 sees raw
  chunk text, not resolved names).

**Collision rows to expect in `review_task`:** S3.4's collision guard writes
`ReviewTaskType.MERGE_CHARACTERS` rows immediately (not deferred to S7) when
contextual evidence blocks what looked like a mergeable pair —
`payload = {"name_a", "name_b", "reason"}`. These two names stay as **separate**
`Character` rows with `collision_suspected=True`; nothing currently blocks S4
relation extraction from treating them as two distinct roster entries, which
is correct — a suspected collision is exactly two candidate people until a
human resolves it.

## be1 → be2 · `api/extraction/similarity.py` expects `cluster_contexts`

S3.3's cascade stage 4 (contextual embedding similarity) calls:

```python
async def cluster_contexts(text_a: str, text_b: str) -> float
```

from `api.graph.similarity` (your S3.8 module, not yet on this branch).
Expected to return a similarity score in `[0, 1]`; `api/extraction/similarity.py`
treats `>= 0.82` as a merge candidate (still subject to the collision guard
before it actually merges). The import is deferred to call time and degrades
to "skip this stage" if `api.graph.similarity` doesn't exist yet in a given
checkout, so nothing on my side needs to change once your branch merges —
stage 4 just starts working. If your actual function name or signature ends
up different, ping me or just match this one; either works, but matching
avoids a second small commit on my side.

## be1 → do1 · chapter_number is genuinely None across the board right now

Per the onboarding brief: `_segment_chapters` (S2.3) finds zero chapters on
`scripts/seed_corpus.py::build_pdf()` output, so every `DocumentChunk.chapter_id`
is null on the real seeded corpus and `CharacterCandidate.chapter_number` /
`Character.first_chapter` / `CharacterAppearance.first_chapter` are `None`
end-to-end for any book ingested through the real pipeline today. This is
**not a bug in S3.1/S3.5** — `discovery.py` and `characters.py` correctly
carry through whatever chapter number the chunk actually has, which is
nothing until your chapter-detection fix lands. Once it does, chapter numbers
should populate with no changes needed on my side (verified via
`api/tests/pipeline/test_extraction_tasks.py`, which exercises the path with
a synthetic chapter-less book and a book with real chapters equally well —
the tests use `chapter_number=None` for their synthetic fixtures, which is
exactly today's real-corpus behaviour).

## be1 → do1 / whoever owns S3.13/S3.14 · what "measured, not assumed" produced

`backend-1.md`'s tiering frozen decision ("resolve it this sprint with
measurement") and the roster P/R/F1 + B³ acceptance criteria both need
do1's labelling harness (S3.13) and a real seeded corpus, neither of which
exist in this worktree (same shape of gap as Sprint 2's chapter-detection
accuracy number — see `plans/sprint-2/HANDOFF.md`'s equivalent note). What
**is** verified from this worktree:

- Roster discovery, rejection, the full alias cascade (all 5 stages),
  collision guard, tiering (both methods), and attribute extraction each
  have unit coverage against synthetic fixtures
  (`api/tests/extraction/*`, 48 tests).
- `test_wuthering_heights_two_catherines` and `test_no_false_splits`
  (`api/tests/extraction/test_two_catherines.py`) are committed as permanent
  regression tests, per the sprint's own acceptance criterion — built
  against a synthetic two-Catherines scenario (full names, a generational
  marker, and a death preceding the second character's introduction) rather
  than the real *Wuthering Heights* text, since no seeded corpus exists here.
- End-to-end wiring of both Celery task bodies against a real Postgres is
  covered in `api/tests/pipeline/test_extraction_tasks.py` (LLM boundary
  stubbed, everything else real, including idempotent re-run).

The actual P/R/F1, B³, and tier-accuracy percentages against real labelled
novels are a Day-5/integration-time measurement once S3.13's harness and a
real corpus exist — recommend this becomes an explicit Day-5 checklist item
exactly as Sprint 2's chapter-detection number was, rather than staying an
implicit be1 DoD box that this worktree cannot honestly fill in.

## be1 → orchestrator · SCR-1 filed (non-blocking)

`TIERING_METHOD` is read from `os.environ` directly in
`api/extraction/tiering.py` rather than through `api.config.settings`
(orchestrator-owned as of the Sprint 2 freeze). See `plans/sprint-3/SCR.md`.
Not blocking — behaviour is identical to a settings field; this is purely
about giving the flag one canonical home.

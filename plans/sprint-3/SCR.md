# Sprint 3 — Schema Change Requests

Checked `plans/sprint-3/SCR.md` in the be1/be2/fe1 worktrees before numbering
these — none of the three had filed one yet as of this writing, so this
starts at SCR-1 (not a guess from a clean slate; Sprint 2's retro records
three agents independently colliding on "SCR-2" from a common ancestor, so
this file exists specifically so nobody has to guess again).

---

### SCR-1 · do1 · 2026-09-22

**Not a schema request — a corpus-fix record, filed per the Day 1/2 priority
in `plans/sprint-3/devops-1.md`.** Recorded here (rather than only in
`HANDOFF.md`) because `plans/sprint-2/RETRO.md` A-2.5 explicitly asked for
"a real SCR... file whichever way you land."

**Problem:** `DocumentChunker._segment_chapters` (be1-owned) found zero
chapters on this corpus. Root cause confirmed directly against the installed
Docling layout model (`docling-layout-heron`, CPU inference, no network):
`scripts/seed_corpus.py::build_pdf()` rendered every line — headings
included — at the same font, size and weight, and Docling's layout model
classifies `SECTION_HEADER` from the rendered page image, not from any PDF
structure tag. Two prior fixes (a larger heading font size alone, then a
`Courier-Bold` heading at the *same* size) were tried in Sprint 2 and ruled
out.

**What was actually tried this time, and what happened** (full method: build
a minimal synthetic PDF varying one visual cue at a time, convert it with the
real installed `docling` package — `PdfPipelineOptions(do_ocr=False)`,
`HF_HUB_OFFLINE=1` — and read `doc.texts[*].label` directly, the same way the
Sprint 2 gap was originally diagnosed):

| Heading treatment (vs. 10pt plain body) | Result |
| --- | --- |
| 10pt plain, centered, isolated by a large blank-line gap | `text` (no change — reproduces the Sprint 2 finding) |
| 10pt **bold**, centered, small gap | `section_header` |
| 12pt plain, left-aligned | `text` |
| **14pt** plain, left-aligned | `section_header` |
| 16-24pt plain, left- or center-aligned | `section_header` |
| 16-24pt **bold**, left- or center-aligned | `section_header` |
| 16-24pt bold, alone on an otherwise-blank page | `section_header` |

**Finding:** font **size** alone crosses Docling's classification threshold
somewhere between 12pt and 14pt on this layout (1.2x-1.4x the 10pt body
size) — bold and centering are not required, though they add margin. This
contradicts the Sprint 2 note that "a heading-specific larger font size...
neither changed Docling's classification"; the two are reconcilable if that
attempt used a modest bump (e.g. 11-12pt, to avoid changing
`CHARS_PER_LINE`/re-wrapping) that never reached the real threshold — nobody
recorded the exact size tried, which is itself worth learning from (see
`HANDOFF.md`).

**Fix landed:** `scripts/seed_corpus.py` now renders a chapter-heading line
(matched by a `_HEADING_RE` local to the script, not a shared import from
be1's `api/pipeline/constants.py:CHAPTER_RE` — `scripts/**` cannot depend on
`api/pipeline/**`, BRANCH.md ownership) in `Courier-Bold` at
`HEADING_FONT_SIZE_PT=16` (1.6x body, comfortable margin above the measured
~1.4x threshold) instead of the 10pt regular body font. `paginate()`'s line
grouping is untouched — a heading still occupies exactly one line-grid slot,
so **no book's page count changed** (verified: 245/211/124/111/685 pages,
identical before and after, for pride-and-prejudice/wuthering-heights/
frankenstein/the-great-gatsby/anna-karenina respectively). Only `pdf_sha256`
changed, because the rendered bytes did.

**Verified against the real, regenerated corpus, not just the synthetic
probe:** ran the genuine `DocumentConverter().convert()` pipeline
(`docling`, the same call path `api/pipeline/chunking.py` uses) against the
rebuilt `corpus/downloads/pride-and-prejudice.pdf`, `page_range=(1, 20)`.
`CHAPTER III.` and `CHAPTER IV.` came back `label=section_header` (confirmed
both via the document-level `doc.texts` view and the per-page raw
`page.predictions.layout.clusters` view, so this is the layout model's own
call, not an artifact of a later merge/reading-order pass). `CHAPTER II.`
did not surface as a distinct item in that same run — traced to a **separate,
pre-existing Docling flake** (`ingestion-pipeline.md` gotcha #7: "the
identical file converted twice in the same process can report a page as
failed on the first attempt"), which fired on 4 of ~20 pages in that specific
`page_range`-limited run; a raw per-page-cluster probe on the same page,
run without hitting that flake, shows `CHAPTER II.` as `section_header`
too. Not a regression from this change — flagged so nobody re-diagnoses it
as one.

**Corpus regenerated:** `make seed --force` (all five books, `.txt` sources
already cached locally so no re-fetch was strictly required, though this run
did re-fetch — see `HANDOFF.md`). `corpus/manifest.json` committed with new
`pdf_sha256` values and two new `layout` fields (`heading_font`,
`heading_font_size_pt`) recording what changed and why. **Sequencing note
for S3.13:** the gold rosters in `eval/gold/**` were labelled *after* this
regeneration, against the *regenerated* corpus's page numbers and
`pdf_sha256` — not the other way around. `eval/loaders.py` enforces this by
refusing to score against a checksum mismatch (test:
`eval/tests/test_loaders.py::test_checksum_mismatch_fails_loudly_not_silently`).

**Not yet done (be1's, not this SCR's):** confirming `_segment_chapters` now
actually assembles chapter rows end-to-end against this corpus is be1's own
S3-adjacent verification once `api/pipeline/**` next runs against it — this
SCR only closes the "Docling never emits a heading label at all" gap, which
was the part blocking be1 categorically rather than by degree.

**Blocking:** no — informational, closes A-2.5.

---

### SCR-2 · do1 · 2026-09-22

**Need:** `MetricsOut`/`StageCost` (`api/contracts/api.py`, frozen at the S3
freeze) to gain fields for GPU KV-cache usage, wall-clock-per-100-pages, and
a dual-rate (local-amortised vs. hosted-API) cost comparison.

**Why:** `plans/sprint-3/devops-1.md` S3.15's acceptance line reads
"`GET /api/ops/metrics?book_id=` returns the full breakdown" including that
exact set of fields. `api/contracts/api.py` cannot be edited mid-sprint
(BRANCH.md), so this sprint the fuller breakdown ships as two new,
locally-defined-response-model endpoints instead:
`GET /ops/extraction-quality` (S3.14) and `GET /ops/extraction-cost`
(S3.15) — both in `api/ops/**`/`api/routes/ops.py` (do1-owned), so no
frozen file was touched to ship them. `GET /ops/metrics`'s own
`prefix_cache_hit_rate` field (already frozen, already present since S2.17)
*is* populated live now (`api/ops/vllm_metrics.py` scrapes vLLM's own
Prometheus endpoint) — that part needed no contract change.

**Blocking:** no — both new fields' data already ships via the two
supplementary endpoints above; this SCR just proposes folding them into the
canonical `MetricsOut` shape at the next freeze so there is one metrics
surface instead of three.

**Proposed:**
```python
class StageCost(BaseModel):
    ...
    cost_usd_api_equivalent: float | None = None
    wall_clock_ms_per_100_pages: float | None = None

class MetricsOut(BaseModel):
    ...
    gpu_kv_cache_usage_pct: float | None = None
```

---

### SCR-3 · do1 · 2026-09-22

**Need:** `api/tests/pipeline/test_books_routes.py::TestStillFrozen::
test_the_openapi_document_still_lists_every_frozen_path` asserts an exact
`len(paths) == 34`. Adding the two S3.14/S3.15 ops routes above
(`GET /ops/extraction-quality`, `GET /ops/extraction-cost`) — both squarely
in do1's owned `api/routes/ops.py` — bumps that to 36. This file is under
`api/tests/pipeline/**` (be1-owned per BRANCH.md); not edited here.

**Why:** this is a real, reproducible failure on `ai/do1/sprint-3-quality`
today (`docker compose --profile test run --rm test pytest
api/tests/pipeline/test_books_routes.py::TestStillFrozen -v`), not a
hypothetical — confirmed the count is what changed (36 paths, all
previously-frozen ones still present; nothing was removed).

**Blocking:** not for do1 — but be2 is also adding routes this sprint
(S3.6/S3.7, `api/routes/characters.py`), so this exact assertion will break
again independently at be2's merge regardless of what happens with this SCR.
Worth considering, at the same time as the count bump: replacing the exact
count with a subset assertion (`frozen_paths <= actual_paths`, or an
explicit frozen-paths list) so a legitimate new route in *anyone's* owned
router stops being a two-agent collision every sprint that adds one.

**Proposed:** either (a) bump `34` to the correct total once all four
agents' branches are known at merge time, or (b) change the assertion's
shape as above. Either way is be1's/orchestrator's call, not do1's — this is
a request, not an edit.

---

### SCR-6 · be2 · 2026-09-22

**Need:** `settings.mention_similarity_threshold: float = 0.65` in
`api/config/settings.py`.

**Why:** S3.8's `cluster_contexts` (`api/graph/similarity.py`) takes
`threshold` as an explicit argument by design (per `plans/sprint-3/backend-2.md`),
but be1's alias cascade (S3.3) needs a place to read the default from rather
than hardcoding a number at its own call site — the whole point of measuring
a precision/recall curve (`plans/sprint-3/HANDOFF.md`) is that the number is
owned by config, not copy-pasted into a second file. `api/config/settings.py`
is orchestrator-owned (BRANCH.md §2), so I cannot add the field myself.

**Blocking:** no. `api/graph/similarity.py::similarity_threshold()` reads it
with `getattr(settings, "mention_similarity_threshold", 0.65)` — the same
`getattr`-with-default pattern SCR-5 (Sprint 2) established for
`settings.reranker_enabled` — so be1 already has a real default to call
`cluster_contexts(..., threshold=similarity_threshold())` against, and
nothing changes at that call site once the field lands.

**Proposed:** add the field to `Settings` in the Sprint 4 freeze (or sooner,
at the orchestrator's discretion — it is a single `float` field, and moving
it does not touch a table or a route).

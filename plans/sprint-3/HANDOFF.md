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

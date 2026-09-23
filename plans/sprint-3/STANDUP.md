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

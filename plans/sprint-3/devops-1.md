# Sprint 3 · DevOps Engineer 1

**Branch:** `ai/do1/sprint-3-quality` · **Worktree:** `../traverse-wt/do1`

## Mission

Make quality a number that moves per commit. Sprint 3 is the first sprint with
accuracy targets, and targets without continuous measurement are decoration.
Build the labelling harness, wire the metrics into CI, and start the cost trend
line for the extraction stage.

## Owned paths

`scripts/**`, `.github/workflows/**`, `api/ops/**`, `eval/**` (new, yours),
`docker*`, `Makefile`

---

## Day 1/2 priority — chapter detection finds zero chapters (carried from Sprint 2, A-2.5)

Before S3.13's gold labels lean on it: `scripts/seed_corpus.py::build_pdf()`
renders the entire novel — headings included — in one uniform, unstyled
Courier. Docling's layout model labels a heading from visual cues alone
(verified directly against the fixture PDF: every line comes back `text`,
never `SECTION_HEADER`/`TITLE`), so `DocumentChunker._segment_chapters`
(be1-owned, only considers those two labels) finds no candidates on either
the CI fixture or the real corpus. `plans/sprint-2/RETRO.md` §4/§5 has the
full writeup, including two things already tried and ruled out (a
heading-specific font size, then a bold Courier variant — same character
width, no re-wrap needed — neither changed Docling's classification).

This does not block S3.13/S3.14 directly (gold labels are page-based, not
chapter-based) but it does block fe1's S3.11 mentions timeline and be2's
S3.6 per-chapter histogram from ever showing real chapter groupings, and it
blocks S3's own DoD line "Extraction stage cost and wall clock per novel
recorded" from meaning anything chapter-scoped. Worth a real fix — more
structural PDF markup (an actual `/StructTree`, or spacing/margin cues
Docling's model responds to, not just font weight/size) rather than another
guess-and-check pass — or an explicit decision that chapter grouping is
deferred until a real-scan-derived corpus replaces the stdlib PDF writer.
File whichever way you land as a fresh SCR either way; do not let it stay an
undocumented gap into Sprint 4.

## S3.13 — Labelling harness

Ground truth for two novels (*Pride and Prejudice*, *Wuthering Heights*):
canonical roster, alias→canonical map, importance tier, first-appearance page.

```
eval/gold/pride_and_prejudice/roster.yaml
eval/gold/wuthering_heights/roster.yaml
eval/schema/roster.schema.json
```

Labelling by hand from scratch is a week's work you do not have. Instead:

1. Seed from public sources (Gutenberg character indexes, published
   concordances) — these are references, not answers, and get verified.
2. `scripts/label_roster.py` — a terminal review tool that walks the system's
   own output and asks a human to confirm, correct, or split, writing YAML.
   Reviewing 60 characters takes an hour; labelling blind takes a day.
3. Version the gold set and **pin it to the corpus manifest checksum** from
   S2.16. Re-pagination invalidates page-level labels, and that must fail loudly.

The tool is reused in Sprint 8 for the question set, so build it to be extended.

*Acceptance:* Both novels labelled and schema-validated. A corpus checksum
mismatch fails the eval run with a clear message.

## S3.14 — Extraction quality in CI

`eval/runners/extraction.py` computing, against the gold set:

- Roster precision / recall / F1
- **B³ precision / recall / F1** for alias clustering (F2.2's metric — implement
  it properly; it is not cluster accuracy and the difference matters)
- Tier accuracy
- Per-cascade-stage contribution, so be1 can see which stage earns its cost
- Rejection precision — how many rejected candidates were real characters

Runs nightly on the GPU host (full novels) and on PRs touching
`api/extraction/**` using a **one-novel reduced set**, so the PR loop stays
under 10 minutes.

Report as a PR comment table with the delta against `ai-master`. A number that
moves silently is a number nobody defends.

**Regression gate ships in Sprint 8 (F6.4), not now** — this sprint the numbers
are informational. Gating before the metric is trusted just teaches people to
skip CI.

*Acceptance:* PR comment renders with current vs. baseline. B³ implementation
verified against a hand-computed toy example committed as a test.

## S3.15 — Extraction cost and throughput

Extend S2.17's metrics for the LLM-heavy stages: tokens in/out per stage per
book, prefix-cache hit rate from vLLM, GPU utilisation and KV-cache pressure
during extraction, wall clock per 100 pages, USD at both local-amortised and
API rates.

**Prefix-cache hit rate is the one to watch.** PRD §5.2's entire cost argument
for Sprint 4's pass 2 depends on it, and be2's S3.9 prototype is measuring it
this week. Make it a first-class dashboard number now so Sprint 4 can watch it
live rather than discovering a regression in the retro.

*Acceptance:* `GET /api/ops/metrics?book_id=` returns the full breakdown.
Nightly job posts the trend. Cache hit rate visible during any extraction run.

---

## DoD

- [ ] Two novels labelled, schema-validated, pinned to the corpus checksum
- [ ] Quality metrics on every relevant PR with a delta table
- [ ] B³ implementation unit-tested against a known example
- [ ] Extraction cost and prefix-cache trend reporting live
- [ ] `HANDOFF.md`: gold-set paths and schema for be1/be2 local runs

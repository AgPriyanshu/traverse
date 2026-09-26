
## be2 — 2026-09-23

**Landed:** S4.1 to S4.7 (pass 2 with stable prefix and length-limit splitting, validator with counted rejections, aggregation, temporal supersession, hearsay, `graph.upsert` with evidence guard, Neo4j-backed reads and routes). Unit tests written for pass 2 and aggregation; integration test for upsert/reads/rebuild.
**Not verified:** anything against real vLLM or real P&P; be1's real signatures; prefix-cache hit rate; precision.

---

# Sprint 4 — Standup

## be1

**Landed (branch `ai/be1/sprint-4-scenes`):**
- S4.8 scene segmentation (`api/pipeline/scenes.py`), repository and query
  helpers (`scene_repository.py`), stage wiring at the tail of
  `resolve_aliases` (`scene_stage.py`).
- S4.9 speaker cascade (`speakers.py`): explicit tag, adjacent narration,
  two-party alternation, batched LLM fallback that halves on `LengthLimitError`.
- S4.10 `pass2_candidates` and `prefilter_stats` (`prefilter.py`).

**Blocked:** the scene tables are not in `api/db/models` or any migration
(SCR-1). The stage skips with a warning until they exist. Query shapes for be2
are in `HANDOFF.md`.

**Found:** S3.4 has no co-presence check to back-fill (see `HANDOFF.md`).

---

## do1 · 2026-09-23

Done: S4.14 harness, gold relations, routes, PR workflow; S4.15 cost report,
rebuild drill and nightly alert; per-worktree test tag, vLLM cache path,
`make ingest`, credential workaround. Next: verification results and push.
Blockers: drill and citation judging need be2's `graph.upsert` and S4.7 routes.
Risk: gold chapter labels are approximate; no Wuthering Heights relations.

---

## fe1

**Landed (branch `ai/fe1/sprint-4-graph`):**
- S4.11 graph explorer at `/books/:id/graph`: Cytoscape with fcose, laid out once over the full graph. Filters (family, tier, confidence, chapter range) are URL params and hide elements in place while the viewport animates. Legend always visible. List view is a full peer, and the default under 48em.
- S4.12 evidence panel (drawer, `Esc` closes, `?edge=` deep-links): header, hearsay qualifier, arc, paginated evidence with page refs, assertion badge and speaker.
- S4.13 relationships on character detail grouped by family, `<RelationArc />` (1, 2 and 3+ states through one path), and the roster sparkline is now real from `CharacterOut.mentions_per_chapter`. `schema.d.ts` was regenerated from the live app (it was stale).
- Contrast test now covers the four relation colours. 166 tests, lint, typecheck and build clean.

**Not done / caveats:**
- Built against the contracts and mocked data only; never seen against be2's real routes or a 900-edge graph, so the "interactive at 900 edges" DoD is unmeasured. The bundle for the graph route is 571 kB (Cytoscape), lazy-loaded.
- Evidence highlight is missing (SCR-10). Chapter filter is derived from page refs (SCR-11).
- Not verified in a browser: 400px, dark mode canvas colours, and the demo recording. Contrast is checked for the palette, not for the rendered canvas.
- `structural` family has no colour token (DCR-5).

## be2 — 2026-09-25

**Real run on live Pride and Prejudice** (project `6146f7d0-…`, book
`4d5750ce-…`), full pass 2 + aggregate + upsert, twice (before/after adding
a second-pass verifier).

- Pass 2 completes in 12.2 min, inside the 25-min budget.
- Zero evidence-free edges, confirmed by direct query on Postgres and Neo4j.
- Prefix-cache hit rate ~68-76% across three runs — **misses the 80% target**,
  not yet root-caused.
- Found and fixed a real bug: roster descriptors leaking into the model's
  "quotes" (493 of 1,753 candidates). Added a verifier second pass.
- **Precision 0.818 / recall 0.273** against do1's gold (`/ops/relation-quality`);
  hand-check of all 28 edges gives ~75-86% depending on how imprecise labels
  are counted. **Neither DoD target (P≥90%, R≥80%) is met** — precision is
  closer than recall, and the verifier traded recall for precision more than
  intended (pre-verifier recall was 0.455, now 0.273).
- Elizabeth/Darcy arc works (two states, cited transition at ch. 58).
- Graph density 1.1% (28 edges / 72 chars) — recommending `co_occurs_with`
  from scene co-presence be built (PRD §12.2), not yet implemented.
- Found a be1-owned roster fragmentation (two Darcy rows, two Collins/Lucas
  rows) that is costing real recall — SCR-16.
- Full details, before/after table and the hand-checked edge list are in
  `HANDOFF.md`.

## be1 — 2026-09-25

**Investigated SCR-18** (be2: Fitzwilliam Darcy / Lady Lucas roster splits,
pass-2 recall 0.273). Finding: not a new bug — both already fixed by
`sprint-4-roster3`; the live roster predated that merge. Re-ran
`resolve_aliases` live directly (no chain, no rebuild needed — worker already
had current code); confirmed both fixed in Postgres. Added regression tests
from the real candidates. `Charlotte Lucas`/`Mrs. Collins` genuinely cannot
merge without a textual marriage cue that isn't in the stored contexts —
documented as a limitation, not fixed. be2's P&P pass-2 numbers were measured
against the stale roster; flagged for a re-run.

## fe1 — 2026-09-26

**Verified S4.11–S4.13 against the real stack** (branch
`ai/fe1/sprint-4-verify`), the item every prior standup entry flagged as
unverified. Result: no `web/src/**` fix needed — the graph explorer, list
view, evidence panel and character-detail relationships all rendered
correctly or degraded gracefully (real `ErrorState` + retry, no crashes, no
console errors) against real data, a transient bad-data window, and a
synthetic 60-node/900-edge stress payload. 400px and dark mode both checked
in a real headless browser. Full local pass clean: lint, tsc, build, and
166/166 tests in `test-web`.

**Found, not fixed (out of `web/src/**` scope):**
- SCR-12 confirmed **not** resolved — `book_id` never filters the graph's
  node list server-side, only its edges (`api/graph/queries.py`). Invisible
  today, will leak in Sprint 5's multi-book projects.
- Filed **SCR-19**: `source.pdf` is missing from the shared MinIO bucket for
  both ingested books, so every page-image request 500s. Citation routing,
  page numbering and the frontend's own error handling are all correct;
  there's simply no image to render right now.
- A transient Neo4j/Postgres desync (Neo4j left pointing at character ids
  `resolve_aliases` had already deleted) made every evidence lookup 404 for
  the first part of this session; self-resolved when a fresh pass-2 run
  (not started by fe1) completed mid-session. Flagged as a retro item — see
  SCR.md — since nothing currently reconciles this automatically.
- Real graph is 73 chars / 29 edges right now, not 900 — noted for context,
  not a bug.

## be2 — 2026-09-26

Found and fixed a real bug: `api/llm/client.py`'s process-wide
`asyncio.Semaphore` broke on the second Celery task in the same worker
(event-loop mismatch) — latent since it was written, not new this sprint.
Regression test added. Re-ran pass 2 after be1's live Darcy/Lucas roster fix:
completion 10.8 min (was 12.2), no crash, evidence-free edges still 0/0.
`GET /ops/relation-quality`: **P 1.0 / R 0.333 / F1 0.5** (was 0.818/0.273/0.409
on the broken roster). Hand-check of all 29 edges: 27 correct, 2 wrong
(pronoun-antecedent misattribution, same class as last time). **Recall is
still well short of the 0.80 DoD target** even with both fixes — the roster
fix helped but isn't the whole story; full details in `HANDOFF.md`.

## do1 — 2026-09-26

**Root-caused S4.15's prefix-cache shortfall.** Two real bugs, one fixed, one
config change landed with a measured before/after: (1) the reported hit rate
was vLLM's lifetime-cumulative average since last boot, not scoped to a book —
wired up the existing (dead) delta helpers into `ingest_book.py`/
`nightly_corpus_ingestion.py`. (2) KV-cache budget was tight (3.05 GiB of
headroom on the 12GB card); raised `--gpu-memory-utilization` 0.75→0.85 (4.25
GiB), measured **67.3% → 75.0%** on a clean controlled A/B (same book, reset
counters). Still short of 80% — the honest remaining reason is structural, not
a bug: hit rate caps at `prefix_tokens/(prefix_tokens+avg_chunk_tokens)`,
measured ≈69.4% for this book's 73-character roster (1,434-token prefix) vs.
its prefiltered chunks (631-token average). Recommend re-deriving the 80%
target per-book from that ratio, or revisiting it. Also found (not fixed,
flagging): the deployed `api`/`celery-worker` image is running be2's
pre-verifier `extract.py`, not current `ai-master`. Full writeup and numbers
in `HANDOFF.md`. Blocked on nothing; next up: full test suite, lint, commit,
push (this session).

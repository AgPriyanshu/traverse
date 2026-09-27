# Sprint 5 — Standup

## fe1 — 2026-09-27

**Landed:** all four stories (S5.9–S5.12) plus the routing refactor they
depend on — characters and the graph moved from `/books/:id/...` to
`/projects/:id/...` in one pass. Project screens (list, create, overview with
drag-to-reorder and an add-book form), the series roster (one row per
character, `<AppearanceStrip>`, "new in book N"), the series graph (client
book filter that animates, a server-side spoiler-safe reading-position
control, appearance-aware node size), and the relationship arc extended
across volumes with book-boundary ticks and per-transition book+page
citations, one code path for a 1-book or 3-book arc.

**Next:** none — this was the full sprint-5 scope for fe1. Would welcome
SCR-1/2 landing (`plans/sprint-5/SCR.md`) so the roster strip's mention
weighting and the multi-book mentions timeline can drop their client-side
workarounds.

**Blocked:** not blocked. Built and tested entirely against the frozen
contracts with realistic mocks (same pattern as Sprint 4's graph explorer);
not yet verified against a live be1/be2 backend, since neither had landed in
this worktree at time of writing.

## be1 — Day 2

**Landed:** S5.1-S5.4, all in `api/reconcile/` (new package):
- S5.1 `pipeline.reconcile_characters` — cascades a book's resolved clusters
  against the project roster (exact/normalised → honorific/name-order → alias
  overlap → embedding → LLM adjudication with series context), reusing
  `api.extraction.normalization`/`similarity`/`collision` rather than
  reimplementing them.
- S5.2 cross-book blocking: `character_death` (hard block, series-position
  aware), kinship contradiction against established `relation` rows,
  generational namesake (reusing the within-book collision guard), and a
  tier-implausibility check on weak-signal (embedding/LLM) matches only.
  Blocked matches queue `merge_across_books` review tasks; every decision,
  matched or blocked or new, gets a `reconciliation_decision` audit row.
- S5.3 appearance + derived-field recomputation, always from the character's
  full appearance set, never accumulated — including `canonical_name` and
  `aliases`, which previously (pre-S5) only ever reflected the most recently
  processed book.
- S5.4 order independence: `test_reverse_order_ingestion_is_checksum_identical`
  ingests a 3-book fixture series both ways and diffs a SHA-256 of the
  project's characters/appearances/aliases/tiers, keyed on series position so
  it's comparable across two separately-created projects.

**Next:** verification pass (targeted, then full suite via
`docker compose --profile test`), then push.

**Blocked:** nothing.

**Note for be2/do1:** see `HANDOFF.md` for the project-roster query shape S5.5
needs and what changed about `Character.canonical_name` stability across
books.

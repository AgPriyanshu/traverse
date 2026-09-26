# Sprint 5 — Standup

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

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

# Sprint 5 standup — do1

## 2026-09-26

**Landed:** S5.13 (series corpus). Extended `scripts/seed_corpus.py` with
series metadata and a `SERIES_CORPUS` list; fetched, licensed and paginated
Anne of Green Gables (6 of 8 books — see HANDOFF.md for why 4 and 6 are
missing) and the four Sherlock Holmes novels, checksums pinned in
`corpus/manifest.json`. `scripts/seed_series.py` + `make seed-series` creates
both series projects and queues their books in order.

**Also landed:** S5.14 (reconciliation eval). Hand-labelled cross-book
identity gold set for Anne 1-3 (13 characters), `eval/identity_metrics.py`
(link P/R, false-merge rate reported separately per devops-1.md, duplicate
rate, order-independence checksum), `GET /ops/reconciliation-quality` +
`GET /ops/reconciliation-order-check`, `make eval-reconciliation`, a PR +
nightly CI workflow. Filed SCR-1 (a frozen route-count test needs bumping,
be1-owned file) and SCR-2 (S5.15 needs a per-project reconcile advisory
lock that only be1 can add, inside `api/pipeline/tasks.py`). Everything here
is real and unit-tested; the live numbers are unverified until be1's
`pipeline.reconcile_characters` (S5.1/S5.2, still a stub in this worktree)
merges — same situation S3.14 was in pre-be1-merge.

**Also landed:** S5.15 (multi-book orchestration). `scripts/ingest_series.py`
+ `make ingest-series PROJECT=<series key>` — sequential by default
(race-free regardless of SCR-2), `--concurrent` as an honest stress-test
harness, `--reverse` for the order-independence check. Per-book cost/time
report plus a roster-growth cost curve (flags superlinear pass-2 cost
growth). All three S5.13/14/15 stories are now implemented and committed.

**Next:** the full verification pass (build, targeted + full test run,
lint) requested at the end of today's session, then push.

**Blocked:** SCR-2 (per-project reconcile lock) blocks a live proof of
S5.15's concurrency DoD line, not the code itself — see SCR.md and
HANDOFF.md. Everything else in this sprint's do1 scope is unblocked.

## 2026-09-27

**Final verification pass done:** `docker compose --profile test build test`
clean; `pytest api/tests -q` → 434 passed, 1 skipped, 1 known failure
(SCR-1's frozen route count, not a regression); `ruff check`/`ruff format
--check` clean; `pnpm lint` (oxlint) clean. Fixed a lint nit found along the
way (line length in `api/ops/reconciliation_quality.py`).

**New finding:** the shared `traverse_test` Postgres database has no
per-worktree isolation (unlike `traverse_be1`/`be2`/`int`) — two concurrent
`docker compose --profile test run` invocations from different worktrees
deadlocked each other on it. Documented in HANDOFF.md and
`.agents/skills/codebase-memory/infra-topology.md`; recommend a
`TEST_POSTGRES_DB` per-worktree suffix as a Sprint 6 action item. Did not fix
in this branch (out of scope for S5.13-S5.15, found only during the final
verification pass).

All three stories (S5.13, S5.14, S5.15) are implemented, committed, and
verified. Pushing `ai/do1/sprint-5-series-corpus`.

## be2 — 2026-09-26

**Landed:** S5.5 (project-scoped, tier-filtered pass-2 roster), S5.6 (series
-position validity — confirmed the (book_order, chapter) mechanism was already
built in Sprint 4; fixed a real gap, a missing `enemy_of -> rival_of` ontology
transition, that would have made the demo's Anne/Gilbert arc report as a
conflict), S5.7 (cross-book aggregation — confirmed already project-wide from
S4, added regression coverage), S5.8 (`/characters/{id}/appearances`
implemented; book-removal cascade — the relations/graph half —
`api/graph/cascade.py`). Also fixed the carried Neo4j `AsyncDriver`
stale-event-loop bug (same class as Sprint 4's semaphore fix), with a
regression test.

**Not verified yet:** full `docker compose --profile test` run (in progress at
time of writing — see this branch's final commit); prefix-cache hit rate and
off-roster rate at series length, which need a real multi-book corpus (do1's
S5.13/S5.14).

**Blocked on nothing**, but flagging for be1: `DELETE /books/{id}`
(`api/routes/books.py`) is still `not_implemented("be1", "S8.8")` — the
book-removal cascade's character-side half (mention/appearance deletion,
orphan sweep, derived-field recompute from remaining appearances) looks like
it belongs to S5.3 but I don't see it landed in this checkout yet. My half
(`api/graph/cascade.py::remove_book`) is ready and tested; integration
contract is in `HANDOFF.md`. The two halves are order-independent (FK cascade
on `character.id` handles the interaction), so no sequencing coordination
needed beyond both existing before `delete_book` is wired up.

---

## be2 — 2026-09-27

**Also fixed:** `relations.repository.replace_project_relations` was
regenerating every `Relation`'s id on every aggregate run (delete + reinsert),
not just on book removal — the same identity-stability bug Sprint 4 fixed for
`Character`. Found via the S5.8 cascade test asserting a surviving relation
kept its id. Now upserts by `(subject, predicate, object)`; regression test
added. See `HANDOFF.md`.

**Verified:** full suite green via `docker compose --profile test build test`
+ `run --rm --no-deps test pytest api/tests -q` (counts in this commit's
message / final report), `ruff check .` and `ruff format --check .` clean
across the whole repo. Branch pushed.

---

# Sprint 5 — Handoff

## fe1 — S5.9 through S5.12

**Routing refactor (one pass, Day 2 per the brief).** Characters and the
graph moved from `/books/:id/characters` / `/books/:id/graph` (S3/S4) to
`/projects/:id/characters` / `/projects/:id/graph`. `/books/:id/...` now
holds only book-local views: overview, chapters, pages, ask, review. A book's
own nav (`bookNav` in `nav-items.ts`) links "Characters" to the project
roster and "Graph" to the project graph pre-filtered to that book
(`?book=<series_order>`), so arriving from a specific book still lands
somewhere relevant. If anything else in the repo (do1's nginx config, an E2E
script, a demo doc) hardcodes `/books/:id/characters` or `/books/:id/graph`,
it needs updating to the project-scoped path — I did not find any outside
`web/src` and `web/tests`, but I did not grep `docker/`, `scripts/`, or
`.github/workflows/`.

**What's built:**

- `/projects`, `/projects/new`, `/projects/:id` (S5.9) — project list, create
  (standalone kind is a one-book project, same code path as series), and the
  book list with drag-to-reorder (native DnD + an up/down-button keyboard
  equivalent), a "recomputing" banner while the reorder mutation and its
  cache invalidation are in flight, and an add-book form with `series_order`
  prefilled to the next open slot.
- `/projects/:id/characters` (S5.10) — one row per character,
  `<AppearanceStrip>` (a per-book presence band with a visible text caption),
  a "new in book N" filter, and a character-detail Appearances section
  (per-book first page, tier, mention count, surface forms, each linking into
  that book).
- `/projects/:id/graph` (S5.11) — a client-side book filter that slices the
  standing graph and animates (same mechanism S4 already used for
  family/tier/confidence), a server-side spoiler-safe series-position control
  (`limit_book_order`/`limit_chapter` — a hard re-fetch, never a client
  filter), appearance-aware node size, and a "first appears in this book"
  badge.
- The relationship arc (S5.12, `<RelationArc>`) now spans volumes: every
  book's chapters laid end to end on one axis, book-boundary ticks, and a
  per-transition citation naming its own book and page. A standalone's
  one-book arc runs through the identical code path (`boundaries.length ===
  1`) as a three-book one.

**Consumed from the backend, as built (not yet verified against a live
be1/be2 API — built against the frozen contracts with realistic mocks, same
pattern as Sprint 4's graph explorer):**

- `GET /projects`, `POST /projects`, `GET /projects/{id}`,
  `PATCH /projects/{id}/order` (be1, `api/routes/books.py`)
- `GET /projects/{id}/characters` (`book_id`, `limit_book_order`,
  `limit_chapter` query params), `GET /characters/{id}`
  (`CharacterDetailOut.appearances`) (be2, `api/routes/characters.py`)
- `GET /projects/{id}/graph` (`limit_book_order`, `limit_chapter`;
  `GraphNodeOut.appears_in_books`, `.first_book_order`;
  `GraphEdgeOut.page_refs[].book_order`), `GET /relations/arc`
  (`RelationOut.first_book_order`/`last_book_order`) (be2, `api/routes/graph.py`)

If any of these shapes differ once be1/be2 land their real implementations,
the two SCRs below are the known, already-worked-around gaps — everything
else should verify cleanly, the same way S4's graph explorer did against the
real backend once it existed.

**Filed:** `plans/sprint-5/SCR.md` SCR-1 (roster-list per-book mention
intensity — degrades to uniform, non-blocking), SCR-2
(`mentions_per_chapter` cross-book ambiguity — worked around client-side,
non-blocking), SCR-3 (the brief's `api/contracts/series.py` doesn't exist;
the five named symbols are real but split across `extraction.py`/
`pipeline.py`/`api.py`), DCR-1 (no canvas artboard or `DESIGN.md` §4 spec for
`project-overview`/`series-roster`/`series-arc` — built from §2's settled
direction and the existing component vocabulary instead).

**Verification (final pass, 2026-09-27):** `docker compose --profile test
build test-web` then `run --rm test-web` — 180 Vitest tests passing across
13 files, oxlint clean (106 files, 116 rules), inside the containerized
runner that matches CI. `pnpm lint`, `pnpm typecheck` (`tsc -b --noEmit`),
and `pnpm build` all clean on the host too. Five commits on
`ai/fe1/sprint-5-series`, pushed.

# Sprint 5 — Handoffs

## be1 → be2, Day 2: the project-roster query shape for S5.5

`pipeline.reconcile_characters` (S5.1-S5.4, `api/reconcile/`) is merged. What
it changed that S5.5's project-scoped pass 2 needs to know about:

**The roster query.** `Character` was already `project_id`-scoped
(`uq_character_project_name`), so the query you want is the same shape
`api/reconcile/repository.py::list_roster_characters` already uses:

```python
select(Character).where(Character.project_id == project_id)
```

No book filter — that's the whole point of S5.5 ("the roster is the
project's, not the book's"). For tier-filtering (protagonist + major always;
minor only when present in *this* book or chapter), join `CharacterAppearance`
on `(character_id, book_id)` — that row's `importance_tier` is the *per-book*
tier (it can legitimately differ from `Character.importance_tier`, which is
now the series-wide max across every appearance, recomputed after every
reconcile — see below). "Present in this chapter" needs `CharacterMention`,
not `CharacterAppearance` (appearance is book-granularity only).

**`Character.canonical_name` can now change after a book you already
processed.** Reconciliation may rename a character's canonical form (e.g. a
book-1 "Anne Shirley" absorbing book-3's "Miss Shirley" settles on whichever
of the character's full alias set is most complete — usually "Anne Shirley",
but not guaranteed) and always recomputes `Character.aliases` as the full
project-wide union, never just the most recent book's. If your pass-2 prompt
caches anything keyed on a character's name string across books, key it on
`Character.id` instead, or re-read the roster fresh per book.

**Ordering for prefix caching.** `reconcile_characters` runs before
`relations.extract` in the frozen chain (`api/tasks.py::STAGES`), so by the
time pass 2 reads the roster for a given book, that book's own reconciliation
has already happened — the roster it sees already reflects any merge this
book's own characters just went through. Sort deterministically as
`character-graph.md` already says; nothing about reconciliation changes that
requirement, it just means the *set* being sorted may include a
newly-recomputed canonical name it wouldn't have on a book processed before
S5.1 landed.

**New column, not a new migration.** `BookCharacterCandidate.resolved_character_id`
(already in the Sprint 1 freeze's model, migration `0006`) is now actually
written, by `resolve_aliases` and repointed by any later merge. Nothing for
you to migrate; mentioned in case you grep for it and want to know who owns
writing it (`api/extraction/repository.py::set_resolved_character_ids`,
`api/reconcile/repository.py::merge_character`).

**Locking.** `reconcile_characters` takes `api/workers/locks.py::
project_roster_lock(project_id)`, a distinct advisory-lock key from
`book_roster_lock`. If S5.5's pass-2 stage ever needs to read-then-write the
roster (it currently only reads), take the same lock rather than inventing a
third one.

# Sprint 5 handoff — do1

## S5.13 — Series corpus

`scripts/seed_corpus.py`'s `CorpusBook` gained series fields (`series_key`,
`project_name`, `project_kind`, `series_order`, `canonical_series_number`).
`SERIES_CORPUS` holds two series, both fetched, paginated and checksummed for
real (this is not a stub — `corpus/manifest.json` and `corpus/LICENSES.md`
are committed with live SHA-256s from the real gutenberg.org fetch):

| Project | Books | Notes |
|---|---|---|
| Anne of Green Gables | 6 of 8 | see below |
| Sherlock Holmes | 4 (novels) | A Study in Scarlet, The Sign of the Four, The Hound of the Baskervilles, The Valley of Fear |

**The sprint brief's premise that "Project Gutenberg has all 8 [Anne] books"
does not hold for gutenberg.org.** Verified directly against the live
catalog rather than assumed: "Anne of Windy Poplars" (1936, the real book 4)
and "Anne of Ingleside" (1939, the real book 6) are still under US copyright
(95 years from publication — until 2031 and 2034) and are not distributed by
the US Project Gutenberg. They exist on gutenberg.net.au under Australian
copyright law (life+70), a different licence regime this corpus deliberately
does not mix in alongside the US-PD Gutenberg License the rest of
`corpus/LICENSES.md` documents. Six books ship instead, `series_order` 1-6
with no gap; each book's true position in the eight-book series is carried
as `canonical_series_number` in `corpus/manifest.json` for documentation.
This does not affect S5.14's gold set (only books 1-3 are labelled) or the
sprint's demo script (only books 1-3 are uploaded).

`make seed` is unchanged — still just the original standalone five, same
runtime budget as before. `make seed --all` (or `--only <series keys>`)
builds the series corpus too. `make seed-series` (new) creates both
projects (`kind=SERIES`) directly in Postgres — `POST /projects` is still
S5.9 (fe1), so this follows the exact precedent `scripts/ingest_book.py`
already set for the standalone project — and uploads each series' books
through the real `POST /projects/{id}/books?series_order=N` in order,
sequentially, idempotent on re-run.

## S5.14 — Reconciliation eval

`eval/schema/identity.schema.json` + `eval/gold/anne_of_green_gables/
identity.yaml`: 13 hand-labelled characters across Anne of Green Gables books
1-3, checksum-pinned per book like `roster.schema.json`/`relations.schema.json`
but multi-book (its own `books` list, one `pdf_sha256`/`page_count` pin per
book). Deliberately includes the cases that matter: Anne's own alias
narrowing, a death (Matthew Cuthbert, book 1 — the primary cross-book
blocking case), a present/present/absent gap appearance (Miss Josephine
Barry), a death near the end of the window (Ruby Gillis, book 3), and three
characters new only in book 3 with no earlier history.

`eval/identity_metrics.py` (pure, unit-tested against a hand-worked toy
example the same way `eval/metrics.py`'s B³ implementation is):
`score_identity_links` (pair-level link precision/recall, false-merge rate,
duplicate rate), `block_precision`, `canonical_graph_checksum`
(order-independent — sorts before hashing, verified by a test that permutes
input order and checks the hash is unchanged).

`api/ops/reconciliation_quality.py` (new do1-owned adapter) reads real
`Character`/`CharacterAppearance`/`Relation` rows for a project, matches each
book's appearances against gold **per book**, not project-wide — a
project-wide match would force one greedy mapping and hide exactly the
failures this eval exists to catch (one gold person split across two
predicted `Character` rows across books = a duplicate; one predicted row
matching two different gold people in two different books = a false merge).
Behind two new routes: `GET /ops/reconciliation-quality?project_id=` and
`GET /ops/reconciliation-order-check?project_id=&compare_project_id=` (the
order-independence hard gate — see SCR-1 for the frozen route-count test
this bumps). `eval/runners/reconciliation.py` + `make eval-reconciliation
PROJECT=<slug>` renders the markdown table; false-merge rate above 1% is a
hard failure (exit 1), never folded into an F1. `.github/workflows/
reconciliation-quality.yml`: a PR-scoped job (books 1-3 only, to bound CI
cost) plus a nightly `order-independence` job that ingests forward and
reverse into two projects and compares checksums.

**Unverified end to end, by design, same situation S3.14 was in before be1's
pass-1 merged:** `pipeline.reconcile_characters` is still
`raise NotImplementedError(...)` in this worktree (`api/pipeline/tasks.py`,
S5.1/S5.2, be1's story, developed in parallel in a separate worktree not yet
merged to `ai-master`). Every function above is real and unit-tested against
synthetic data; what is not yet checked is the live number this produces
against the real Anne corpus, because the stage the number depends on does
not exist in this branch's history yet. It will start reporting real numbers
the moment be1's reconcile lands and re-runs through `make seed-series` +
`make eval-reconciliation` — no code change needed here, matching the
`extraction-quality.yml` precedent from Sprint 3.

One finding worth flagging early: `Character` is already unique on
`(project_id, canonical_name)` (migration 0006, Sprint 3), and Sprint 4's
retro (finding 7) says `resolve_aliases` already upserts by that key. That
means a **naive** baseline — two books whose pass-1 canonicalizes the same
surface form to the exact same string — may already partially link across
books today, before S5.1/S5.2's smarter cascade lands, which is worth
checking first rather than assuming today's number is zero.

## S5.15 — Multi-book orchestration

`scripts/ingest_series.py` + `make ingest-series PROJECT=<series key>`:
queues an entire series through the real API in order. Sequential by
default (upload one book, poll to terminal, then the next — always
race-free regardless of whether the reconcile lock in SCR-2 exists yet);
`--concurrent` fires every upload immediately as a deliberate stress test.
`--reverse` uploads in reverse sequence while every book keeps its true
`series_order` — the mechanism the order-independence checksum check
(S5.14's `GET /ops/reconciliation-order-check`) depends on.

Per-book report: wall clock, pass-1/pass-2 local-amortised cost
(`GET /ops/extraction-cost` / `/relation-cost`), roster size after that book
(`GET /projects/{id}` `character_count`), aggregated into a
**roster-growth cost curve** — the ratio of (pass-2 cost growth) to (roster
size growth) between consecutive books, flagged if it runs consistently
above ~1.15 (superlinear). This is plumbing, not yet a measured number:
running it for real needs the reconcile stage merged (same dependency as
S5.14).

**Per-project reconcile lock (SCR-2): not built by do1, cannot be.** The
lock has to be acquired inside the Celery task
(`_reconcile_characters`/`api/pipeline/tasks.py`) where the transaction
actually runs; `api/pipeline/**` and `api/workers/**` are be1-owned, and
`scripts/**` genuinely cannot reach into that process. `--concurrent` is
built as an honest stress-test harness (fires every upload with no
between-book wait) rather than a fake "proof" — flagged to the orchestrator/
be1 in SCR-2 rather than silently assumed to exist.

## Verification

Everything in this handoff is real, unit-tested code (`eval/tests/`,
`scripts/test_ingest_series.py`, `scripts/test_label_roster.py` all pass
locally: `pytest eval/tests scripts/test_label_roster.py
scripts/test_ingest_series.py -q`). What is **not** verified is a live
number from a real multi-book ingestion run, because
`pipeline.reconcile_characters` (be1, S5.1/S5.2) is still a stub in this
worktree's history — the same position S3.14's extraction-quality eval was
in before be1's pass 1 merged (`plans/sprint-3/HANDOFF.md`). Re-run
`make seed-series && make eval-reconciliation PROJECT=anne-of-green-gables`
and `make ingest-series PROJECT=anne-of-green-gables` once be1/be2's Sprint 5
work lands on `ai-master` — no code change should be needed here for real
numbers to start appearing.

## Final verification pass (2026-09-27)

`docker compose --profile test build test` (clean build, no credentials
workaround needed this time), `run --rm --no-deps test pytest api/tests -q`:
**434 passed, 1 skipped, 1 known failure** (`TestStillFrozen::
test_the_openapi_document_still_lists_every_frozen_path`, `40 == 38` — SCR-1,
not a regression). `ruff check`/`ruff format --check` clean; `pnpm lint`
(oxlint) clean, 0 warnings/errors on 96 files (no `web/**` touched this
sprint, ran anyway per the verification pass).

**New finding, not a regression in this branch's own code:** two concurrent
`docker compose --profile test run` invocations from different worktrees
(this one tagged `do1`, another tagged `dev`) deadlocked each other against
the shared `traverse_test` Postgres database — one run's fixture connection
sat `idle in transaction` holding a lock the other run's `TRUNCATE
ingestionstage, ingestionrun, ...` teardown needed, and vice versa via lock
queueing, and both suites hung at the same ~46-49% mark until one container
was removed. Confirmed by inspecting `pg_stat_activity` mid-hang. Separately,
the shared `db`/`rabbitmq` containers were restarted by another agent's
action while a test run was mid-flight, producing `AdminShutdown`/
"database system is starting up" connection errors — again not code, just
timing. Unlike `traverse_be1`/`traverse_be2`/`traverse_int`
(BRANCH.md §4), **`traverse_test` has no per-worktree isolation** — every
worktree's `test` service points at the same database, unlike the live-stack
databases. This is the same class of gap Sprint 4's retro flagged for the
MinIO bucket (A-4.2: "any shared test/live resource needs isolation from day
one"), just on the Postgres side and for concurrent *test* runs rather than
test-vs-live. Not fixed here (out of scope for this sprint's three stories,
and a `docker-compose.yml`/`.env.example` change needs care); recommend a
`TEST_POSTGRES_DB` override keyed the same way `TEST_IMAGE_TAG` already is
(`${TEST_IMAGE_TAG}` suffix) as a Sprint 6 action item. Waiting for a clear
window (`docker ps --filter name=traverse-test-run-` empty) and retrying
worked reliably.

## Known carried infra items (spot-checked, not re-investigated)

- **Test/live MinIO bucket isolation** (SCR-19, Sprint 4): `docker-compose.yml`'s
  `test` service still overrides `MINIO_BUCKET: ${TEST_MINIO_BUCKET:-traverse-test}`,
  `.env.example` still lists `traverse-test` in `MINIO_BUCKETS`, and
  `docker/minio/init-buckets.sh`'s fallback default still includes it. Still
  in place.
- **Per-worktree test image tag** (A-3.2): `Makefile`'s
  `export TEST_IMAGE_TAG ?= $(notdir $(CURDIR))` and
  `docker-compose.yml`'s `image: traverse-api-test:${TEST_IMAGE_TAG:-...}`
  are both still there. Still in place.

## For the orchestrator / be1

See `plans/sprint-5/SCR.md` SCR-1 — do1 cannot implement the per-project
reconcile advisory lock itself (`api/pipeline/**` is be1-owned), but S5.15's
acceptance criterion depends on it existing. Flagged rather than silently
assumed.

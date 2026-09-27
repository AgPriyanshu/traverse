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

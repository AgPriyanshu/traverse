# Sprint 5 — Handoff

## be2 → all · project-scoped pass 2, series-position, cross-book aggregation, project graph APIs (S5.5 – S5.8)

**Most of the series-position and cross-book-aggregation mechanism was already
built in Sprint 4** — `Relation`/`RelationEvidence` were `(book_order,
chapter)`-shaped from the S4 freeze, `relations.aggregate` already grouped by
`(subject, predicate, object)` project-wide, and `relations.tasks
._aggregate_relations` already pulled every other book's standing evidence
into each book's aggregate run. S5.6/S5.7 in this branch are mostly closing
real gaps found while confirming that, not building the mechanism from
scratch — see the codebase-memory `character-graph.md` diffs in this branch
for exactly which rows flipped from `S5` to `Built` and why.

### S5.5 — project-scoped roster

`api/relations/repository.py::load_project_roster(session, book_id)` replaces
`load_book_roster` as pass 2's roster source (`relations/tasks.py
._extract_relations`). Protagonist and major characters are always included,
project-wide; minor and mentioned characters are included only when *this*
book has an appearance or a mention for them. Computed once per book (not per
chunk or per chapter), which is what keeps the prompt prefix byte-identical
within a book — `choose_roster`'s `MAX_PROMPT_ROSTER` tier-drop still runs on
top as the safety net for a roster this filter alone doesn't shrink enough.
`load_book_roster` still exists for book-local views (e.g. a future review UI
listing "this book's cast"); nothing in pass 2 calls it anymore.

**Not measured this branch** (needs a real multi-book corpus, do1's S5.13/
S5.14 territory): whether the off-roster rate actually holds flat as the
series grows, and whether the prefix-cache hit rate holds ≥80% once the roster
is a project's worth of names rather than one book's. Flagging now so it is
checked at integration, not assumed.

### S5.6 — series-position validity

The row-comparison machinery (`(first_book_order, first_chapter) <= (:b,
:c)`), the `SeriesPosition` type, and `graph/repository.py`'s and
`graph/queries.py`'s reading-position filters were already in place. The
actual gap: `api/graph/ontology.yaml`'s `transitions` list was missing
`{from: enemy_of, to: rival_of}` — the exact transition the Sprint 5 demo
script's Anne/Gilbert arc needs (enemies → rivals → friends). Without it,
that pair reported as an unresolved conflict (`resolve_conflict` review task)
instead of a supersession. Added; `rival_of -> friend_of` and `enemy_of ->
friend_of` were already legal, so the arc's other two transitions needed
nothing.

### S5.7 — cross-book aggregation

Confirmed, not rebuilt: `relations.aggregate.aggregate()` groups by
`(subject_id, predicate, object_id)` with no book dimension in the key, so a
predicate reasserted in a later book always extends the same state's evidence
list rather than opening a new one — the "genuine re-establishment vs.
supersession" distinction the story calls out was already correct, because
`_apply_transitions` only ever runs *between* distinct `(s, p, o)` states of
one character pair, never within one. `RelationEvidence.book_order` was
already on every evidence row. Added `relations.repository.load_project_facts`
(a supersede of `load_facts_from_other_books`, kept as a thin wrapper for the
existing call site) as the shared "all standing evidence, optionally minus one
book" primitive S5.8's cascade also needs.

**Found while writing S5.8's cascade test, fixed here since it is the same
bug class**: `relations.repository.replace_project_relations` deleted and
reinserted every non-human-verified `Relation` row on *every* aggregate run
(an ordinary pass-2 rerun, not just a book removal), which regenerated every
edge's id and cascade-deleted-then-recreated its evidence each time — the
exact bug class Sprint 4 fixed for `Character` via `persist_characters`'s
upsert-by-natural-key, just not yet applied to `Relation`. Now upserts by
`(subject_character_id, predicate, object_character_id)`: an existing row's
id and its evidence are kept for an edge aggregation still produces, updated
in place; only a relation aggregation no longer produces is deleted. This is
the identity-stability guarantee the orchestrator specifically asked to be
checked for book removal — it turned out to already be broken for an
ordinary rerun, not just removal. Regression test:
`test_cross_book_aggregation.py::test_relation_id_is_stable_across_reaggregation_reruns`.

### S5.8 — project graph APIs and book removal

- `GET /projects/{id}/graph`, `GET /relations/arc`, `GET
  /characters/{id}/neighbourhood`, `GET /graph/path` were already built and
  wired (S4). `GET /characters/{id}/appearances` was a stub
  (`not_implemented`) — implemented now via
  `graph/repository.py::list_appearances`, reusing the exact reading-position
  gate `get_character` already applies (a character not yet met is hidden
  entirely, not just its appearance list).
- **Contract shapes are unchanged**: `GraphOut` (`nodes: GraphNodeOut[]`,
  `edges: GraphEdgeOut[]`, `truncated`), `RelationArcOut` (`states:
  RelationOut[]`, ordered by series position), position filtering is
  `limit_book_order`/`limit_chapter` throughout (not a combined
  `position_lte` tuple — that shorthand in the sprint plan's route table is
  notation, not a different wire shape; every existing route and contract
  already uses the two-field form and I kept it consistent rather than
  introducing a second convention).
- **Not done this branch**: a `tiers=` multi-value filter on `/projects/{id}
  /graph` (the plan's route table mentions it; `list_characters`/`get_graph`
  today only filter by `families`/`min_confidence`/`book_id`/single `tier`).
  Scoped out to keep this branch to real correctness gaps; flagging for
  whoever picks it up next (S5.9 or later) rather than filing an SCR since it
  is additive and not a schema change.

**Book removal (PRD §12.1b) — integration contract with `DELETE
/books/{id}`** (`api/routes/books.py`, be1-owned, currently
`not_implemented(OWNER, "S8.8")` — note the story tag there reads S8.8, not
S5.8; not mine to fix, flagging in case it is a typo rather than a deliberate
re-scope):

- `api/graph/cascade.py::remove_book(session, project_id, book_id)` is the
  be2-owned half: deletes this book's `RelationEvidence` rows explicitly (safe
  whether or not the `Book` row itself has been deleted yet — `RelationEvidence
  .book_id` already cascades on the `Book` FK, so this is idempotent either
  way), reaggregates every edge from what Postgres still holds
  (`cascade.reaggregate_project`, reusing `relations.aggregate` — an edge with
  no evidence left simply does not come back), then re-projects Neo4j via the
  existing `graph.upsert.upsert_project` (not a bespoke removal projection).
- **Character-side cleanup is be1's S5.3 concern**: deleting this book's
  `CharacterMention`/`CharacterAppearance` rows (an existing primitive,
  `api/extraction/repository.py::delete_book_characters`, already does the
  delete half — it just isn't hooked to book *removal* yet, only to a
  same-book rerun), sweeping a `Character` left with zero appearances
  (`sweep_orphaned_characters`, same caveat), and recomputing derived fields
  (`first_book_id`, `first_chapter`, series-wide tier, mention count) from
  whatever appearances remain. That recompute-from-remaining-appearances step
  does not exist yet as far as I can see in this checkout — it may be part of
  what S5.3 is landing.
- **The two sides are order-independent**, which is what makes this a clean
  handoff rather than a sequencing puzzle: `Relation.subject_character_id`/
  `object_character_id` are `ON DELETE CASCADE` on `character.id`, so deleting
  an orphaned `Character` row cascades away every `Relation` naming it
  automatically, regardless of whether `cascade.remove_book` ran first. Call
  `cascade.remove_book` from `delete_book` any time after the `Book` row (or
  at least its evidence) is gone; calling it before or after the character
  sweep both converge on the same final graph.
- Regression test: `api/tests/graph/test_cascade.py` — a relation with
  evidence in two books survives removal of one with its evidence and counts
  recomputed; a relation only the removed book evidenced does not come back;
  removing a book that evidenced nothing is a no-op.

### Carried bug fix (not a numbered story)

`api/graph/client.py`'s `AsyncDriver` singleton had the same stale-event-loop
bug the Sprint 4 retro already found and fixed for `api/llm/client.py`'s
semaphore: each Celery task is its own `asyncio.run(...)`, so a driver (and
the lock guarding its construction) built on one task's loop raised
`RuntimeError: ... attached to a different loop` on the next task's loop.
`get_driver()` now tracks the loop it built on and rebuilds — best-effort
closing the stale driver, since the loop that owned its connections has
usually already closed by the time the mismatch is detected — whenever the
running loop differs. Regression test in `api/tests/graph/test_client.py`
mirrors `api/tests/llm/test_client.py`'s semaphore test: two separate
`asyncio.run()` calls against `get_driver()`.

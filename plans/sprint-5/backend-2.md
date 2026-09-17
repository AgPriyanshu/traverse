# Sprint 5 · Backend Engineer 2

**Branch:** `ai/be2/sprint-5-series-graph` · **Worktree:** `../traverse-wt/be2`
**Owned:** `api/graph/**`, `api/relations/**`, `api/query/**`, `api/llm/**`,
`api/routes/{graph,characters}.py`

## Mission

Make the graph a *series* graph: one edge per relationship regardless of how many
volumes establish it, validity measured in series position, and an arc that
spans books. Pass 2 now reads against the project roster, which is what lets
book five state a fact about a book-one character and have it land on the right
node.

---

## S5.5 — Project-scoped pass 2

The prompt prefix now carries the **project** roster, not the book's. This is
the mechanism that makes a series one graph rather than N graphs.

It also breaks the roster budget. *Anne of Green Gables* across eight books is
150+ named characters; Sherlock Holmes is worse. The tier-filtered roster
designed in Sprint 4 stops being an optimisation:

- protagonist + major tier: **always** present
- minor + mentioned: only when they appear in **this book**, or are mentioned in
  this chunk's chapter
- record which strategy a book used — it is an ablation row in Sprint 8

**Prefix stability still governs cost.** The roster must be byte-identical across
every call *for a given book* — it may legitimately differ between books, since
each book's tier filter differs. Sort deterministically; key the prefix cache per
book; verify the hit rate stays ≥80% and does not silently degrade as the roster
grows. If it does degrade with series length, that is a finding for the retro and
a real limit worth publishing.

*Acceptance:* A relation in book 3 whose subject first appeared in book 1
resolves to the book-1 character. Off-roster rate does not rise with series
length — if it does, the tier filter is dropping characters the text still uses.

## S5.6 — Series-position validity (F3.3)

Replace chapter-scalar windows with `(book_order, chapter)` tuples:
`first_book_order`, `first_chapter`, `last_book_order`, `last_chapter`.

Compare with **row comparison**, which Postgres supports natively and which is
clearer and faster than a synthetic composite ordinal:

```sql
WHERE (r.first_book_order, r.first_chapter) <= (:book_order, :chapter)
```

A standalone book is `(1, chapter)`, so there is exactly one code path — no
branch on project kind anywhere.

Legal-transition logic from Sprint 4 is unchanged; only the ordering key moves.
Anne↔Gilbert: `enemy_of` (1, 4) → `rival_of` (1, 15) → `friend_of` (3, 8) is
three edges chained by supersession, not one edge rewritten three times.

*Acceptance:* An arc spanning three books returns in order with the transition
citation at each step, each naming its book.

## S5.7 — Cross-book aggregation

Aggregation key becomes `(project_id, subject, predicate, object)` after inverse
normalisation. Sirius is Harry's godfather in book 3 and again in book 5: **one
edge, evidence from both**, `first_book_order = 3`.

Watch two things:

- **Do not merge a genuine re-establishment with a supersession.** The same
  predicate reasserted in a later book extends the evidence set; a *different*
  predicate supersedes. That distinction is `is_legal_transition`, and it is now
  doing more work than in Sprint 4.
- Evidence rows carry `book_id` and `book_order`. A citation without its book is
  useless in a series — "page 214" of which volume?

*Acceptance:* An edge established in three books has one row and three books'
worth of evidence, ordered by series position.

## S5.8 — Project graph APIs and book removal

```
GET /api/projects/{id}/graph      ?book_id=&families=&tiers=&position_lte=
GET /api/projects/{id}/characters
GET /api/characters/{id}/appearances
GET /api/relations/arc?a=&b=      ordered, per-book citations
DELETE /api/books/{id}
```

`?book_id=` returns **that book's slice of the standing graph** — nodes
appearing in it, edges with evidence from it — not a separate per-book graph.
The distinction is the whole feature.

`position_lte` takes `(book_order, chapter)`. Sprint 8's reading-position
spoiler mode is then a parameter, not a refactor.

**Book removal cascades by evidence, never by character** (PRD §12.1b). Deleting
book 3: drop its chunks, mentions, appearances, and evidence rows; then drop any
*edge* left with zero evidence and any *character* left with zero appearances.
Anne survives with two appearances and recomputed derived fields; Davy and Dora,
appearing only in book 3, go.

*Acceptance:* Removing the middle book of a three-book project leaves a
consistent graph — no orphan edges, no characters with zero appearances, derived
fields recomputed. Neo4j re-projects and matches.

---

## DoD

- [ ] Pass 2 resolves cross-book subjects; prefix-cache hit rate holds ≥80%
- [ ] Series-position comparison used everywhere; zero branches on project kind
- [ ] One edge per relationship across the series, evidence from every book
- [ ] Arc API returns multi-book transitions with per-book citations
- [ ] Book removal verified to leave no orphans
- [ ] `HANDOFF.md`: `GraphOut` with appearance data, `RelationArcOut`, position filter shape

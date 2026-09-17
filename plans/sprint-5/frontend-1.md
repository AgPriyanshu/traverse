# Sprint 5 · Frontend Engineer 1

**Branch:** `ai/fe1/sprint-5-series` · **Worktree:** `../traverse-wt/fe1`
**Owned:** `web/src/**`, `web/tests/**`

## Design input

Read [design/DESIGN.md](../../design/DESIGN.md); this sprint adds the
`project-overview`, `series-roster`, and `series-arc` artboards. Load `dataviz`
before the appearance strip and the arc — both are timeline forms and they must
read as one system.

The whole product surface moves up a level: routes become `/projects/:id/...`
with `/books/:id/...` surviving only for book-local views (pages, chapters).
That is a routing refactor; do it in one pass on Day 2 rather than screen by
screen.

---

## S5.9 — Project screens

- **`/projects`** — list. Each card: name, kind, book count, character count,
  cover strip of spines.
- **`/projects/new`** — name + kind (`standalone` | `series`). A standalone is a
  one-book project; do not build a second flow for it.
- **`/projects/:id`** — books in series order, each with ingestion status.
  **Drag to reorder**, which `PATCH`es `/projects/{id}/order` and triggers
  recomputation — show that it is recomputing, because the roster visibly
  changes underneath the user.
- **Add book** — upload with `series_order` prefilled to the next slot and
  editable. Books may arrive in any order; the UI must not imply otherwise.

*Acceptance:* A three-book series is created, uploaded, and reordered without
leaving the project screen. Reordering shows its effect rather than silently
mutating the roster.

## S5.10 — Series roster

`/projects/:id/characters`. One row per character with an **appearance strip** —
a small horizontal band of book slots, filled where the character appears,
intensity by mention count.

The strip is the screen's reason to exist: "appears in books 1, 2, and 5" is the
single most useful fact about a character in a series, and it is unreadable as
text. Anne fills every slot; Davy fills slots 3 onward; a one-book character
shows a single mark.

- "New in book N" filter — the returning reader's most common question
- Per-book alias display: hovering a slot shows the surface forms used in that
  book
- Character detail gains an **appearances** section: per-book first page, tier,
  mention count, aliases, each linking into that book

*Acceptance:* A reader can answer "which books is this person in, and where do
they first appear in each" in one glance. Strip is legible at 400px and has a
text equivalent for screen readers — a coloured band alone is not an answer.

## S5.11 — Series graph

Extend Sprint 4's explorer:

- **Book filter** — the standing graph's slice for that book. The animation
  between slices is the feature; a hard swap reads as a different graph.
- **Series-position range** — two-handled control over `(book, chapter)`
- Node badges for "first appears in this book"
- Legend gains appearance encoding without becoming a second legend

Keep the list view at parity. On a series it is arguably the primary view —
"every relationship Anne has, grouped by book" is more useful on a phone than
any force layout.

## S5.12 — Series arc

Extend `<RelationArc>` from a chapter timeline to a **series timeline**: book
boundaries marked, segments per relationship state, a cited marker at each
transition.

Anne ↔ Gilbert across three books — enemies, rivals, friends — with the page in
the right volume at each turn is the single most persuasive image this product
can produce. It is the Sprint 5 demo screenshot. Build it with that in mind.

A single-book arc must render through the same component and code path.

*Acceptance:* Arcs render correctly for 1 book / 1 state, 1 book / 3 states, and
3 books / 3 states. Every transition cites book and page.

---

## DoD

- [ ] Routing moved to project scope in one pass
- [ ] Appearance strip legible, accessible, and text-equivalent
- [ ] Book filter animates between slices of one graph
- [ ] Arc spans volumes with per-book citations, one code path for all shapes
- [ ] 400px and dark mode clean throughout

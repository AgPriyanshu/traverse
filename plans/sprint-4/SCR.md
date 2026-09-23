# Sprint 4 — Schema Change Requests

fe1 numbers from SCR-10 and DCR-5 (DCR-1 to DCR-4 were Sprint 3) so a common-ancestor collision with be1's SCR-1 or be2's next number cannot happen again (see `plans/sprint-2/RETRO.md`).

---

### SCR-10 · fe1 · 2026-09-23

**Need:** an optional `span: SpanBox | None` on `EvidenceOut`, the same shape `SpanBox` already has for page-viewer highlights.

**Why:** S4.12 acceptance is "every evidence item reaches its page in one click with the right span highlighted". `EvidenceOut` has `quote`, `page_start` and `page_end` but no coordinates, and `PageRenderOut.spans` cannot be tied to a quote client-side. Today the evidence item links to the page (`<PageRef>`) with no highlight.

**Blocking:** no. One click reaches the page; only the highlight is missing. Same gap as Sprint 3 SCR-9 (`MentionOut.span`), and the same fix, probably in the same stage.

**Proposed:** `span: SpanBox | None = None` on `EvidenceOut`, populated where `relation_evidence` is written. fe1 will append `?highlight=x,y,w,h` to the `<PageRef>` link as soon as it exists (the page route already parses that parameter).

### SCR-11 · fe1 · 2026-09-23

**Need:** first and last chapter on `GraphEdgeOut` (`first_chapter: int | None`, `last_chapter: int | None`), matching `RelationOut`.

**Why:** the graph filters by chapter range and the relationship rows show a chapter span. `GraphEdgeOut` carries only `page_refs`, so fe1 derives chapters by joining each ref's page against `/books/{id}/chapters`. That works but is approximate (only the cited pages, not the relation's true validity range) and is exactly the hook Sprint 8's spoiler slider needs to be exact.

**Blocking:** no.

**Proposed:** add both fields, additive and defaulted to `None`.

### SCR-12 · fe1 · 2026-09-23

**Need:** `GET /api/projects/{id}/graph` documented as book-scoped by `book_id`, and confirmation that a single-book project's `book_id` filter returns character nodes only for that book.

**Why:** the screen is `/books/:id/graph`. fe1 calls it with `project_id` from `BookOut` and `book_id` set. If `book_id` is ignored the book screen silently shows the whole series.

**Blocking:** no, assuming the filter works as its name says.

---

### DCR-5 · fe1 · 2026-09-23

**Need:** a `relation.structural` colour token (light and dark), plus a line-style entry for it in `design/DESIGN.md` §3.

**Why:** the ontology and `RelationFamily` have five families; §3 defines four colours and four line styles. fe1 draws `structural` in the muted ink (`fg.muted`, 5.6:1 light and 7.0:1 dark) with a long-dash pattern `16 3` so it is still distinguishable by line style. That is a placeholder, not a design.

**Blocking:** no.

**Proposed:** one token, validated at 4.5:1 on paper, surface and sunken in both themes. `tests/contrast.test.ts` already checks the four existing relation colours, so the new one only needs adding to its list.

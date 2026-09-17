# Sprint 2 — Schema & Contract Change Requests

Carried in from Sprint 1. Non-blocking requests batch into the Day-1 freeze.

### SCR-1 · be2 · carried from Sprint 1 · ACCEPTED for the Sprint 2 freeze

**Need:** `GraphEdgeOut.page_refs` is `list[int]` and carries no book dimension.

**Why:** relations are project-scoped, so an edge's evidence can come from more
than one volume. `page_refs: [47, 214]` cannot say which book either page is in
— and in a series a citation without its book is not a citation. This is the
only citation surface in the contracts with that hole. The Neo4j projection
already stores `"<book_order>:<page>"`, so the read path currently discards the
book on the way out.

**Blocking:** no. Bites at Sprint 5 (series) at the latest, and the frozen
contract is what fe1 generates its client from, so it moves at a freeze rather
than mid-sprint.

**Proposed:** a `PageRefOut {book_id, series_order, page}` struct, used by
`GraphEdgeOut.page_refs` and anywhere else a bare page number is returned.
Orchestrator lands it in migration/contract freeze for Sprint 2.

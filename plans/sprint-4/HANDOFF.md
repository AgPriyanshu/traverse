# Sprint 4 — Handoff

## fe1 → be2

- The graph screen calls `GET /api/projects/{project_id}/graph?book_id=...` with the book's `project_id`. It renders `nodes`, `edges`, and `truncated`, filters client-side, and needs `page_refs` on every edge (the chapter filter and span derive from them, SCR-11).
- Edge click calls `GET /api/relations/{id}/evidence?limit=10&offset=n` and expects chapter-ordered results with the sort key stable across pages. The client re-sorts within a page only.
- The evidence panel calls `GET /api/relations/arc?a=<source>&b=<target>` using the edge's `source` and `target`. States need `first_chapter`, `last_chapter` (null = open ended) and `page_refs[0]` as the transition citation; a state with no page ref renders "no page cited".
- Character detail uses `GET /api/characters/{id}/neighbourhood?depth=1` and reads only its edges touching the character.
- `GraphEdgeOut.evidence_count` sets the edge width and the panel's "of N" total.

## fe1 → orchestrator

- `web/src/lib/api/schema.d.ts` was regenerated from `app.openapi()` (the committed file predated the Sprint 4 freeze). Docstrings now appear as comments, which is generator behaviour.
- New deps: `cytoscape`, `cytoscape-fcose` (no types, so `web/src/types/cytoscape-fcose.d.ts`).
- Filed SCR-10, SCR-11, SCR-12 and DCR-5 in `plans/sprint-4/SCR.md`.

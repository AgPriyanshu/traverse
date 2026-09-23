
## fe1

**Landed (branch `ai/fe1/sprint-4-graph`):**
- S4.11 graph explorer at `/books/:id/graph`: Cytoscape with fcose, laid out once over the full graph. Filters (family, tier, confidence, chapter range) are URL params and hide elements in place while the viewport animates. Legend always visible. List view is a full peer, and the default under 48em.
- S4.12 evidence panel (drawer, `Esc` closes, `?edge=` deep-links): header, hearsay qualifier, arc, paginated evidence with page refs, assertion badge and speaker.
- S4.13 relationships on character detail grouped by family, `<RelationArc />` (1, 2 and 3+ states through one path), and the roster sparkline is now real from `CharacterOut.mentions_per_chapter`. `schema.d.ts` was regenerated from the live app (it was stale).
- Contrast test now covers the four relation colours. 166 tests, lint, typecheck and build clean.

**Not done / caveats:**
- Built against the contracts and mocked data only; never seen against be2's real routes or a 900-edge graph, so the "interactive at 900 edges" DoD is unmeasured. The bundle for the graph route is 571 kB (Cytoscape), lazy-loaded.
- Evidence highlight is missing (SCR-10). Chapter filter is derived from page refs (SCR-11).
- Not verified in a browser: 400px, dark mode canvas colours, and the demo recording. Contrast is checked for the palette, not for the rendered canvas.
- `structural` family has no colour token (DCR-5).

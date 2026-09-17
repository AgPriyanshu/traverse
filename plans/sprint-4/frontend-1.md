# Sprint 4 · Frontend Engineer 1

**Branch:** `ai/fe1/sprint-4-graph` · **Worktree:** `../traverse-wt/fe1`

## Mission

Build the screen that sells the product. PRD F3.6 is blunt about it: the graph
explorer exists substantially because it demos beautifully — *and it must be
real*, backed by the same store the retriever queries. Your job is to make a
900-edge graph legible, and to make every edge one click from the pages that
prove it.

## Design input — read before writing any component

Open [design/DESIGN.md](../../design/DESIGN.md) and the canvas URL recorded
there; this sprint implements the `graph-explorer` and `evidence-panel`
artboards. Relation-family colours come from the `relation.*` tokens — and per
DESIGN.md §3 they must be paired with a **line style**, so colour is never the
only channel carrying meaning. File a DCR rather than adding a colour.

## Owned paths

`web/src/**`, `web/tests/**`

---

## S4.11 — Graph explorer

`/books/:id/graph`. Cytoscape.js (better typed-edge styling than
react-force-graph, and `fcose` layout handles this density well).

- **Nodes** sized by importance tier, labelled with canonical names. Labels on
  minor characters hide below a zoom threshold — 60 overlapping labels is not a
  visualisation.
- **Edges** coloured by family *and* styled by family (solid / dashed / dotted).
  Width by evidence count — a relation with 40 citations should look heavier
  than one with 2.
- **Filters:** family, importance tier, minimum confidence, chapter range.
  Filtering re-runs the layout with animation, so the user sees *what changed*
  rather than a new unrelated picture. This is also the mechanism Sprint 8's
  spoiler slider reuses — build it so the chapter filter is already the hook.
- **Legend** mapping colour + style → family, always visible. A graph that needs
  a tooltip to interpret its own colours has failed.
- Click node → character detail. Click edge → evidence panel (S4.12).
- Layout is computed once and cached; recomputing `fcose` on every filter change
  makes the graph jump and feels broken.

**The accessible equivalent is a requirement, not a nice-to-have** (PRD §6,
NFR-a11y): a "List view" toggle rendering the same filtered data as a structured
per-character relationship list, keyboard navigable, with the same click-through.
Build it in this story, not as a follow-up — it is also genuinely the better view
on a phone.

*Acceptance:* 60 nodes / 900 edges stays interactive (pan, zoom, filter without
jank). Legible at 400px via list view. Every filter combination reachable by
keyboard.

## S4.12 — Evidence panel

Opens on edge click. **This is the product's core promise made concrete.**

- Header: `Elizabeth Bennet — married_to → Fitzwilliam Darcy`, family badge,
  confidence, evidence count
- **Relationship arc** (S4.13's component) when the pair has one
- Evidence list, chapter-ordered: quote, `<PageRef>`, chapter, assertion badge
  (narrated / dialogue / inferred), speaker when dialogue
- `hearsay` edges carry a visible qualifier — "asserted in dialogue by Mrs
  Bennet", not presented as narrative fact
- Click any page ref → page viewer at that page with the quote highlighted,
  using the coordinate contract agreed in Sprint 2
- Paginate; an edge can carry 40+ evidence items

*Acceptance:* Every evidence item reaches its page in one click with the right
span highlighted. Panel is keyboard-navigable and closes on `Esc`.

## S4.13 — Relationships on character detail + arc view

Fill the placeholder from Sprint 3. Group a character's relationships by family,
each row showing the other party, predicate, evidence count, and chapter span,
opening the evidence panel on click.

**`<RelationArc />`** — the temporal sequence from F3.3, rendered as a horizontal
chapter timeline with segments per relationship state and a cited marker at each
transition. A single-state relationship renders as one segment through the same
code path — no special case.

This component is the visual argument for something most graph extractors get
wrong, so it is worth the care: "friends, ch. 1–7 → estranged, ch. 8–end" with
the transition page cited is a picture no chatbot can produce.

*Acceptance:* An arc renders correctly for a flat relationship, a single
transition, and a three-state sequence. Every transition marker cites a page.

---

## DoD

- [ ] Graph interactive at 900 edges; list view is a genuine equal, not a stub
- [ ] Every edge one click from its evidence, every evidence item one click from its page
- [ ] Arc component handles 1, 2, and 3+ states through one path
- [ ] Colour never the sole carrier of meaning; contrast ≥ 4.5:1 in both themes
- [ ] **Record the demo** — this is the ship gate and the footage is a GTM asset

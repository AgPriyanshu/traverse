# Sprint 4 — Relationship Graph · **SHIP GATE**

**Goal:** a character knowledge graph where every edge is typed, directed,
temporally bounded, and click-through to the pages that prove it.

**PRD refs:** F3.1 – F3.6 · PRD §5.2 pass 2

**This is the ship gate.** After this sprint the project is a portfolio piece
even if nothing else ships. Everything from Sprint 6 on makes it better; this
sprint makes it *exist*. Protect the scope accordingly — an idea that arrives on
Wednesday goes in the backlog, not the sprint.

---

## Inputs from Sprint 3

be2's S3.9 prototype already answered: does the roster fit the context, does
prefix caching engage, is Qwen3-8B adequate, does it invent off-roster
characters. **Plan Day 1 against those findings, not against the PRD's
assumptions.** If the prototype said the roster does not fit, the tier-filtered
roster design below is load-bearing rather than an optimisation.

## Contract freeze (Day 1)

| Item | Detail |
|---|---|
| Migration `0009` | `relation`, `relation_evidence` tables; unique `(subject_id, predicate, object_id, first_chapter)`; FK cascade on evidence; indexes on `(book_id, predicate)` and `(subject_id)`/`(object_id)` |
| `contracts/graph.py` | `ExtractedRelation`, `AggregatedRelation`, `EvidenceItem`, `Predicate`, `RelationFamily`, `AssertionType` |
| `contracts/api.py` | `GraphOut {nodes, edges}`, `RelationOut`, `EvidenceOut`, `RelationArcOut` (the temporal sequence) |
| Routes | `GET /projects/{id}/graph`, `GET /characters/{id}/neighbourhood`, `GET /relations/{id}/evidence`, `GET /relations/arc`, `GET /graph/path`, `GET /graph/ontology` |

---

## Scope

| Story | Owner | Summary |
|---|---|---|
| S4.1 | be2 | `relations.extract` — pass-2 roster-informed extraction with prefix caching |
| S4.2 | be2 | Off-roster validator — reject any subject/object not a known character |
| S4.3 | be2 | `relations.aggregate` — dedupe to one edge with N evidence items (F3.5) |
| S4.4 | be2 | Temporal validity — transitions close edges rather than overwrite (F3.3) |
| S4.5 | be2 | Assertion provenance — narrated / dialogue / inferred + speaker (F3.4) |
| S4.6 | be2 | `graph.upsert` — Neo4j projection with denormalised page refs, evidence enforced (F3.2) |
| S4.7 | be2 | Graph read APIs — subgraph, neighbourhood, path, evidence |
| S4.8 | be1 | Scene segmentation + co-presence index — pass-2's candidate filter |
| S4.9 | be1 | Speaker attribution for dialogue lines — feeds F3.4 |
| S4.10 | be1 | Pass-2 chunk prefilter: only chunks with ≥2 roster mentions |
| S4.11 | fe1 | Graph explorer — force-directed, typed edges, filters (F3.6) |
| S4.12 | fe1 | Edge evidence panel — every quote with its page, click to viewer |
| S4.13 | fe1 | Relationship panel on character detail + the relationship arc view |
| S4.14 | do1 | Relation quality eval — per-predicate P/R, citation page accuracy |
| S4.15 | do1 | Pass-2 cost and cache-hit reporting; graph rebuild-from-Postgres drill |

---

## Demo script (Day 5) — this is the portfolio demo

```bash
make up && make ingest BOOK=pride_and_prejudice
```

1. `/books/:id/graph` — the Bennet household, the Darcy/Bingley circle, and the
   Longbourn↔Netherfield social network, laid out legibly.
2. Filter to **kinship** — the family tree stands alone and is *correct*.
3. Click the Elizabeth ↔ Darcy edge → evidence panel with quotes and pages.
4. Click a page ref → the viewer opens at that page with the span highlighted.
5. Elizabeth ↔ Darcy shows a **temporal arc**, not one flat label: antagonistic
   early, `married_to` by the end, with the transition chapter cited.
6. A dialogue-sourced edge is visibly attributed ("according to Mrs Bennet").
7. `/graph/path?from=Heathcliff&to=Cathy` on *Wuthering Heights* returns a path
   with every hop cited.
8. `make graph-rebuild BOOK=…` wipes Neo4j and rebuilds from Postgres — the
   graph comes back identical.

## Definition of Done

- [ ] Relation precision ≥ 90%, recall ≥ 80% on major-character pairs (PRD §1.3)
- [ ] **Zero edges without evidence** — enforced at upsert, verified by a query
- [ ] ≥ 95% of sampled citations land on a page that supports the claim (F3.2)
- [ ] Temporal arcs work on at least three known relationships
- [ ] Neo4j fully rebuildable from Postgres
- [ ] Pass-2 cost per novel and prefix-cache hit rate recorded
- [ ] **PRD §12.2 resolved** — measure graph density and decide `co_occurs_with`
- [ ] `RETRO.md` written, and the demo recorded — this is the ship gate

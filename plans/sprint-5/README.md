# Sprint 5 — Series & Reconciliation

**Goal:** upload the books of a series into one project and get **one** graph —
a returning character is the same node gaining a new appearance, and a
relationship arc spans volumes.

**PRD refs:** F1.1, F2.5, F3.1, F3.3, F3.6 · §3.5

## Why here, and why not earlier

The schema has been project-scoped since migration `0006` — `character` and
`relation` are keyed on `project_id`, and `character_appearance` has existed
since Sprint 3. That was nearly free at the Sprint 1 freeze and would cost a
full re-migration of characters, relations, and the Neo4j projection now. This
sprint adds the **behaviour** that schema was waiting for.

It sits **after** the ship gate so Sprint 4 was never delayed, and **before**
the query layer so the router, Cypher templates, retrieval filters, and citation
format are built project-aware from the first line. Retrofitting project scope
through those afterwards is most of a sprint of rework.

Through Sprints 1–4 every project has exactly one book, so reconciliation was
trivially "everything is new". Nothing needs unwinding.

## Contract freeze (Day 1)

Migration `0010` — behaviour, not restructuring:

- `reconciliation_decision(book_id, candidate_cluster_key, character_id, method, confidence, blocked_by, decided_at, human_verified)` — the audit trail. Every link, every new character, every block, with its reason.
- `project.roster_version` — bumped on every reconcile so caches and the graph projection know they are stale
- `character_death(character_id, book_id, chapter, evidence_id)` — the primary cross-book blocking signal
- indexes: `character_appearance (book_id)`, `relation (project_id, first_book_order)`

`contracts/series.py`: `ReconcileCandidate`, `ReconcileDecision`, `SeriesPosition`, `AppearanceOut`, `RelationArcOut`.

## Scope

| Story | Owner | Summary | PRD |
|---|---|---|---|
| S5.1 | be1 | `pipeline.reconcile_characters` — cascade against the project roster | F2.5 |
| S5.2 | be1 | Cross-book blocking evidence — death, kinship contradiction, namesake | F2.5 |
| S5.3 | be1 | Appearance records + derived-field recomputation | F2.3, F2.5 |
| S5.4 | be1 | Order independence — reverse upload produces an identical graph | §3.5 |
| S5.5 | be2 | Project-scoped pass 2 — the roster is the project's, tier-filtered | §5.2 |
| S5.6 | be2 | Series-position validity — `(book_order, chapter)` windows and arcs | F3.3 |
| S5.7 | be2 | Cross-book aggregation — one edge, evidence from every book | F3.5 |
| S5.8 | be2 | Project graph APIs + `/relations/arc`; book removal cascade | F3.6 |
| S5.9 | fe1 | Project screens — create, book list, drag-to-reorder, add book | F1.1 |
| S5.10 | fe1 | Series roster — per-book appearance strip, "new in this book" | F2.5 |
| S5.11 | fe1 | Series graph — book filter, series-position range, appearance-aware nodes | F3.6 |
| S5.12 | fe1 | Series relationship arc across volumes | F3.3 |
| S5.13 | do1 | Series corpus — *Anne of Green Gables* 1–8, *Sherlock Holmes* | §7 |
| S5.14 | do1 | Reconciliation eval — link precision/recall, false-merge rate | F6.2 |
| S5.15 | do1 | Multi-book orchestration — queue a whole series, per-book cost | F7.1 |

## Demo script (Day 5)

```bash
make up && make seed-series
```

1. Create project "Anne of Green Gables", kind `series`.
2. Upload books 1–3 with `series_order` 1, 2, 3. All three ingest.
3. `/projects/:id/characters` — **one** Anne Shirley, not three. Her appearance
   strip shows all three books; Davy and Dora show only book 3.
4. Anne → appearance timeline across volumes; aliases differ per book
   ("Anne Shirley" → "Miss Shirley" as she becomes a teacher).
5. Anne ↔ Gilbert Blythe arc: **enemies (bk 1) → rivals (bk 1–2) → friends
   (bk 3)**, each transition cited with its book and page.
6. `/projects/:id/graph` — the series graph. Filter to book 2: the standing
   graph's book-2 slice, not a separate graph.
7. Reading position = book 2, chapter 5 → everything later disappears.
8. **The order-independence test:** new project, upload 3 → 2 → 1. Graph is
   identical to the forward-order one, verified by checksum.
9. Remove book 3 → Davy and Dora go; Anne survives with two appearances and
   recomputed first/last.

## Definition of Done

- [ ] Cross-book link precision ≥ 95%, recall ≥ 90%, **false merges ≤ 1%**
- [ ] Reverse-order upload produces a checksum-identical graph
- [ ] Every reconciliation decision has an audit row with its reason
- [ ] A relationship arc spans volumes with per-book citations
- [ ] Book removal cascades by evidence, never by character
- [ ] A standalone book still works — it is a one-book project, same code path
- [ ] `RETRO.md`, and PRD §12.1a / §12.1b resolved with measured numbers

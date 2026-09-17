# Backlog — PRD requirement traceability

Every functional and non-functional requirement in [traverse-prd.md](../traverse-prd.md)
mapped to the sprint and agent that delivers it. If a requirement is not in this
table, it is not being built.

Legend — **Owner:** `be1` backend ingestion/characters · `be2` backend
graph/query · `fe1` frontend · `do1` devops · `orch` orchestrator (contract
freeze).

---

## F1 — Ingestion

| Req | Summary | Sprint | Owner |
|---|---|---|---|
| F1.1 | Async upload, book_id in <3s, per-stage progress | 2 | be1 + fe1 |
| F1.2 | Staged Celery pipeline, per-stage retry, dead-letter, resume | 2 | be1 |
| F1.3 | Page provenance mandatory, rejected at upsert if absent | 2 | be1 |
| F1.4 | Chapter segmentation, regex + LLM fallback, ≥95% boundary recall | 2 | be1 |
| F1.5 | Idempotent re-ingest by content hash; human_verified preserved | 2 | be1 |
| F1.1s | Projects — create, upload into, set and change series order | 5 | fe1 + be1 |
| §3.5 | Order-independent ingestion — reverse upload yields an identical graph | 5 | be1 |

## F2 — Character extraction & resolution

| Req | Summary | Sprint | Owner |
|---|---|---|---|
| F2.1 | Pass-1 discovery, token-budgeted batching, ≥95% recall | 3 | be1 |
| F2.2 | Alias clustering cascade; name-collision split; B³ F1 ≥ 0.85 | 3 | be1 |
| F2.3 | Character record — aliases, tiers, first/last page, attributes | 3 | be1 |
| F2.4 | Non-character rejection with stored reason | 3 | be1 |
| F2.5 | Cross-book reconciliation — link returning characters, ≤1% false merges | 5 | be1 |

## F3 — Relationship graph

| Req | Summary | Sprint | Owner |
|---|---|---|---|
| F3.1 | Ontology: nodes, predicate families, inverses, symmetry | 4 | be2 |
| F3.1s | Project + Character-appearance nodes; project-scoped identity | 1 schema, 5 behaviour | orch, be1 |
| F3.2 | Evidence mandatory on every edge, enforced at upsert | 4 | be2 |
| F3.3 | Temporal validity — chapter windows, status transitions | 4 | be2 |
| F3.3s | Series-position validity `(book_order, chapter)`; multi-volume arcs | 5 | be2 |
| F3.4 | Assertion provenance — narrated / dialogue / inferred + speaker | 4 | be2 |
| F3.5 | Aggregation and conflict resolution | 4 | be2 |
| F3.6 | Graph explorer UI | 4 | fe1 |
| F3.6s | Series graph — book filter as a slice of one standing graph | 5 | fe1 |

## F4 — Question answering

| Req | Summary | Sprint | Owner |
|---|---|---|---|
| F4.1 | Query router — 6 classes | 6 | be2 |
| F4.2 | Graph-constrained retrieval before vector fallback | 6 | be2 |
| F4.3 | Templated Cypher, never free-form | 6 | be2 |
| F4.4 | Grounded streaming answers with page citations | 6 | be2 + fe1 |
| F4.5 | Spoiler-safe **reading position** (book + chapter), leakage 0 | 8 | be2 + fe1 |
| F4.6 | Conversational follow-up with carried scope | 6 | be2 |

## F5 — Human review

| Req | Summary | Sprint | Owner |
|---|---|---|---|
| F5.1 | LangGraph interrupts, Postgres checkpointer, restart-safe | 7 | be2 |
| F5.2 | Six task types (incl. `merge_across_books`) | 7 | be2 |
| F5.3 | Keyboard-first queue, 50 tasks in <8 min | 7 | fe1 |
| F5.4 | Durable cascading corrections, human_verified never overwritten | 7 | be1 + be2 |

## F6 — Evaluation

| Req | Summary | Sprint | Owner |
|---|---|---|---|
| F6.1 | Gold dataset — 2 novels + a 3-book series labelled, ≥60 questions | 8 | be1 (labelling tooling) |
| F6.2s | Reconciliation metrics — link P/R, **false merges reported separately** | 5 | do1 |
| F6.2 | Metrics — roster F1, B³, relation P/R, citation acc, ECE, leakage | 8 | be2 |
| F6.3 | Ablations — the published table | 8 | be2 + do1 |
| F6.4 | CI regression gate, −2pt fails the PR | 8 | do1 |

## F7 — Ops

| Req | Summary | Sprint | Owner |
|---|---|---|---|
| F7.1 | Cost telemetry per book per stage, per query | 9 | do1 |
| F7.2 | Performance telemetry, GPU/KV pressure, queue depth | 9 | do1 |
| F7.3 | Model routing policy editor with live cost/quality delta | 9 | do1 + fe1 |
| F7.4 | Pipeline health, dead-letter depth, Langfuse trace links | 9 | do1 + fe1 |

## Non-functional (PRD §6)

| Req | Summary | Sprint | Owner |
|---|---|---|---|
| NFR-perf | First token ≤1.5s p95, answer ≤6s p95, ingest ≤25min/350pp | 6, 9 | be2, do1 |
| NFR-rel | Stage retry/resume, idempotency, restart-safe interrupts | 2, 7 | be1, be2 |
| NFR-residency | Fully local default path, API routing labeled in UI | 9 | do1 + fe1 |
| NFR-obs | Full Langfuse tracing, stage timing, token accounting | 1, 9 | do1 |
| NFR-a11y | Keyboard nav, 4.5:1 contrast, non-visual graph equivalent | 7, 9 | fe1 |
| NFR-deploy | Cold `docker compose up` working in <5 min, CPU + GPU profiles | 1, 9 | do1 |

## Copyright & ethics (PRD §10)

| Req | Summary | Sprint | Owner |
|---|---|---|---|
| ETH-1 | Public demo serves public-domain only, enforced in code | 9 | do1 |
| ETH-2 | Uploads private, deletable, never pooled | 9 | be1 + do1 |
| ETH-3 | Quote-length cap on cited spans | 6 | be2 |
| ETH-4 | Local inference default; API routing explicit and labeled | 9 | do1 + fe1 |

---

## Deferred (PRD §3.2 / §3.4) — not in this eight-sprint plan

| Item | Why deferred | Revisit |
|---|---|---|
| Event / plot graph | Ship-gate scope discipline; evidence rows already support it | Post-launch |
| EPUB ingestion | No page numbers conflicts with the headline promise (PRD §12.1) | Sprint 9 |
| Non-English source text | BGE-M3 already multilingual; blocker is prompts and eval labor | Post-launch |
| Fine-tuning | PRD §3.2 — prompting and routing only | Out of scope |
| Multi-tenancy | Demo workspace only | Post-launch |
| OCR path for scanned PDFs | Docling tesserocr is installed but untuned; public-domain corpus is digital | Sprint 9 if time, else post-launch |

---

## Open PRD decisions and when they get resolved

| PRD §12 | Decision | Resolve in |
|---|---|---|
| 1 | EPUB in v1 or v1.1 | Sprint 9 retro |
| 2 | `co_occurs_with` on by default | Sprint 4 (measure graph density first) |
| 1a | Reconciliation auto-link threshold | Sprint 5 — from a measured P/R curve |
| 1b | Book removal cascade semantics | Sprint 5 |
| 3 | Demo upload allowance | Sprint 9 |
| 4 | Open-source scope | Sprint 9 |
| 5 | Importance tiering method | Sprint 3 (measure, don't guess) |

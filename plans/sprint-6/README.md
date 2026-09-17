# Sprint 6 — Query & Citations

**Goal:** ask "how does Elizabeth know Mr Darcy" in plain English, get a grounded
streaming answer with inline citations, and click one to land on the page.

**PRD refs:** F4.1 – F4.4, F4.6 · ETH-3 · NFR-perf

**Build everything project-aware from the first line.** Sprint 5 made characters
and relations project-scoped with series-position validity; the router, Cypher
templates, retrieval filters, and citation format must carry project scope and
book-bearing citations natively. Retrofitting that afterwards is most of a
sprint — which is exactly why Sprint 5 sits before this one.

Planning note: this sprint is specified to story level. Re-plan it to task level
at its Day-1 freeze, absorbing Sprint 4's retro — particularly whatever the
relation-quality numbers say about which query classes are trustworthy.

## Contract freeze (Day 1)

Migration `0011`: `query_log` (per PRD §5.5), `conversation`, `conversation_turn`.
`contracts/query.py`: `QueryRequest`, `QueryEvent` SSE union — **explicitly
discriminated** on `type` so `openapi-typescript` generates a usable union rather
than `unknown` (fe1 raised this risk in Sprint 1) — `CitationOut`, `RouteDecision`.

## Scope

| Story | Owner | Summary | PRD |
|---|---|---|---|
| S6.1 | be2 | Query router — 6 classes, with a measured confusion matrix | F4.1 |
| S6.2 | be2 | Templated Cypher library, one template per class; **no free-form Cypher** | F4.3 |
| S6.3 | be2 | Graph-constrained retrieval — resolve names → node/edge evidence → vector fallback | F4.2 |
| S6.4 | be2 | Grounding check + abstention; ungrounded claims dropped, not softened | F4.4 |
| S6.5 | be2 | SSE streaming answers with inline citation events | F4.4 |
| S6.6 | be2 | Conversation memory — carried character and chapter scope | F4.6 |
| S6.7 | be1 | Character name resolution service — "Lizzy", "Darcy", "her sister" → character IDs | F4.1 |
| S6.8 | be1 | Quote-span locator: given a quote, return page + bounding boxes for highlighting | ETH-3 |
| S6.9 | be1 | Answer-latency instrumentation per stage (route, retrieve, generate) | NFR-perf |
| S6.10 | fe1 | Ask screen — streaming answer, inline citation chips, suggested questions | F4.4 |
| S6.11 | fe1 | Citation click-through → page viewer with the quote highlighted | F4.4 |
| S6.12 | fe1 | Clarifying-question interrupt UI (the router's ambiguous path) | F4.1 |
| S6.13 | fe1 | Conversation thread view with per-turn citations | F4.6 |
| S6.14 | do1 | Answer quality harness — accuracy, citation precision, abstention rate | F6.2 |
| S6.15 | do1 | Latency budget enforcement in CI; p95 and TTFT trended | NFR-perf |

## Demo script

1. "Who is Mr Collins?" → answer with citations, each clicking to a page.
2. "How does Elizabeth know Mr Darcy?" → relationship path, every hop cited.
3. "Who are all of Mr Bennet's daughters?" → **exactly five**, from the graph,
   not a plausible four assembled from prose (F4.1).
4. "What happens to Elizabeth's brother?" → *abstains.* She has no brother, and
   saying so is the correct answer (F4.4).
5. "And her sister?" → resolves against the previous turn (F4.6).
6. "What happens at the end?" on a book only half-read → ambiguity handled; full
   spoiler enforcement lands in Sprint 8.
7. First token under 1.5s; full answer under 6s, shown in the ops panel.

## Definition of Done

- [ ] Answer accuracy ≥ 85%, citation precision ≥ 95%, abstention ≥ 90% on the
      Sprint 6 question set
- [ ] Aggregation queries **exhaustive** — verified against gold rosters
- [ ] Router confusion matrix published; misroutes analysed in the retro
- [ ] p95 ≤ 6s, TTFT ≤ 1.5s, measured on the integration host
- [ ] Zero free-form Cypher reaches the database — asserted by test
- [ ] `RETRO.md` written

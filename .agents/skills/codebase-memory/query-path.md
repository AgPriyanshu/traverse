# Query & citation path

Question → route → graph-constrained retrieval → grounded answer → clickable
page. Symbols over line numbers.

## Key symbols

| Symbol | Location | Status |
| --- | --- | --- |
| `GraphState`, `responder`, `get_agent` | `api/llm.py` | Built — **prototype; a single node doing raw cosine-distance top-5. Replaced in S6.** |
| WebSocket `/ws` echo + agent invoke | `api/main.py` | Built — prototype |
| Route stubs, all 33 paths with real response models | `api/routes/*.py` | **Built — frozen** |
| Hybrid retrieval (pgvector + `ts_rank_cd` + RRF) | `api/retrieval/hybrid.py` | S2 |
| Cross-encoder reranker (flagged) | `api/retrieval/` | S2 |
| Query router | `api/query/router.py` | S6 |
| Cypher template library | `api/query/templates/` | S6 |
| Graph-constrained retrieval | `api/query/` | S6 |
| Grounding check / abstention | `api/query/` | S6 |
| SSE streaming | `api/routes/query.py` | S6 |
| `resolve_names`, `locate_quote` | `api/pipeline/` | S6 |
| Spoiler enforcement | query layer, all surfaces | S8 |

## Route classes (S6)

| Class | Path |
| --- | --- |
| Character lookup | character record + per-book appearances + top evidence |
| Relationship lookup | direct edge query + evidence |
| Path / connection | shortest-path traversal, each hop cited |
| Aggregation | constrained graph query — **exhaustive**, never a plausible subset from prose |
| Narrative / free text | graph-scoped hybrid retrieval + generation |
| Series arc | how a pair's relationship changed across volumes, cited per transition |
| Ambiguous | clarifying-question interrupt back to the user |

Router returns class **and** extracted entities in one structured call — a second
entity pass doubles latency on the critical path.

## Retrieval order — graph first

1. resolve names → character IDs (`resolve_names`, <50ms, **never an LLM call**)
2. pull node and edge evidence chunks
3. hybrid search **within that constrained set**
4. whole-book vector search — last resort only

Log which tier answered. The ablation table needs the breakdown, and it is the
writeup's central claim.

Hybrid = dense (pgvector cosine, top 50) + lexical (`ts_rank_cd`, top 50) fused
with **reciprocal rank fusion, k=60**. RRF rather than score normalisation — the
two scores are not commensurable and normalising them is where hybrid search
usually goes wrong.

## Citation rules

- Every factual claim carries **book** + chapter + page, resolving to the
  rendered page with the span highlighted. In a series a citation without its
  book is not a citation.
- Default query scope is the **project**; a single book is a filter, not a
  different endpoint.
- **A quote that `locate_quote` cannot find is dropped, not cited.** A citation
  to the wrong span is worse than no citation.
- Quotes are capped at 400 chars (ETH-3, PRD §10 — the system is a finding aid,
  not a reader).
- Ungrounded claims are **removed** from the answer, and the answer says what it
  could not establish. "Not established in this novel" is a correct answer;
  hedging to a technically-non-false statement is not.
- `hearsay` edges are attributed ("According to Mrs Bennet…"), never stated as
  narrative fact.

## SSE contract (S6)

Discriminated event union — switch on `type`, never parse by shape:

```
token | citation | route | interrupt | done | error
```

Citations stream as their own events so the UI renders chips inline as the
sentence arrives. **`proxy_buffering off` must be set in nginx** or streaming
silently hangs in the containerised deploy — it is set in S1 with a comment
saying why.

## Templated Cypher — never free-form

The LLM selects a template ID and fills named slots; it never emits Cypher.
Slots are validated against the ontology before execution. There is a test
asserting no code path can send a model-authored string to Neo4j. Cap
`max_hops` at 4 — an uncapped shortest path on a dense graph is a
self-inflicted denial of service.

## Spoiler scoping — reading position (S8)

The scope is a **reading position**: `(book_order, chapter)`, not a bare chapter.
It is a **required field on the query context object**, not an optional argument;
`None` meaning "no limit" must be an explicit choice at the call site. Enforced
in three places, all of which must hold:

1. graph — `(first_book_order, first_chapter) <= (:b, :c)`
2. retrieval — filter chunks by their book's order and chapter
3. generation — the model only ever sees filtered context

Target leakage: **zero**, measured by an automated test across answers,
citations, graph payloads, and character lists. Never enforced by instructing
the model.

The parameter has been plumbed through retrieval since S2 precisely so this is a
config change, not a refactor.

## Related

[character-graph.md](character-graph.md) · [llm-runtime.md](llm-runtime.md) ·
[.agents/rules/graph-query.md](../../rules/graph-query.md) ·
[plans/sprint-6/](../../../plans/sprint-6/)

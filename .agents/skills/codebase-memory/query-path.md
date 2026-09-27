# Query & citation path

Question → route → graph-constrained retrieval → grounded answer → clickable
page. Symbols over line numbers.

## Key symbols

| Symbol | Location | Status |
| --- | --- | --- |
| WebSocket `/ws` echo + agent invoke | `api/main.py` | Built — prototype, unrelated to search now that `api/llm.py` is gone |
| Route stubs, all 33 paths with real response models | `api/routes/*.py` | **Built — frozen** |
| `GET /graph/ontology`, `/projects/{id}/characters`, `/characters/{id}`, `/projects/{id}/graph` | `api/routes/{graph,characters}.py` | **Built** — Postgres-backed reads; `/graph` moves to Neo4j in S4.7 |
| LangGraph Postgres checkpointer (`checkpointer`, `setup_checkpointer`) | `api/graph/checkpoint.py` | **Built** — survives a SIGKILL; see character-graph.md |
| `dense_search`, `lexical_search`, `embed_query` | `api/retrieval/repository.py` | **Built** — `character_ids` is a real filter now (`CharacterMention` `EXISTS` subquery, S6.3), not accepted-and-ignored |
| `hybrid_search` (RRF, k=60) | `api/retrieval/hybrid.py` | **Built** — `GET /api/search` wired to it; `SearchResultOut.tier` is `"graph_constrained"` or `"unconstrained"` |
| Cross-encoder reranker (`rerank`, `reranker_enabled`) | `api/retrieval/rerank.py` | **Built**, flag default off — no measured quality lift and CPU latency over budget on the Sprint 2 smoke set; see `plans/sprint-2/RETRO.md` before turning it on |
| Query router (`classify_question`, `RouterOutput`) | `api/query/router.py` | **Built** (S6.1) — one structured call returns class + entity phrases. Targets the frozen 7-value `QueryRoute` enum: PRD F4.1 names 6, `series_arc` was added on top for series support (S5.6's `/relations/arc`). Uses `LLMPurpose.ADJUDICATE` as an interim stand-in — no dedicated routing purpose exists yet (SCR-2, `plans/sprint-6/SCR.md`) |
| Cypher template library (`TEMPLATES`, `run_template`, `resolve_aggregation_predicate`, `required_gender`) | `api/query/templates.py` | **Built** (S6.2) — one declared, parameterised statement per class that needs Neo4j (`relationship_lookup`, `aggregation`); `character_lookup`/`series_arc` reuse existing Postgres repository reads instead of a second Cypher statement, `path` reuses `graph.queries.shortest_path`. `run_template` rejects any slot set not matching the declared params exactly. Structural proof (AST scan, no dynamically-built query reaches `.run()`/`.execute_query()`): `api/tests/query/test_no_freeform_cypher.py` |
| Graph-constrained retrieval (`retrieve_for_narrative`) | `api/query/retrieval.py` | **Built** (S6.3) — constrained hybrid search first, whole-project fallback only when the constrained set is empty; logs which tier answered |
| Grounding check / abstention (`ground_narrative_answer`, `abstain`) | `api/query/grounding.py` | **Built** (S6.4) — the five graph-derived classes are grounded by construction (`api/query/generation.py` renders straight from a retrieved record/`RelationOut`); `narrative` alone free-generates, checked by a deterministic content-word-overlap threshold against its own retrieved chunks — not semantic entailment, a documented limitation |
| Gendered aggregation filter (`infer_gender`) | `api/query/gender.py` | **Built** (S6.1/S6.4) — the ontology carries no gender attribute, so "Mr Bennet's daughters" vs "...sons" is disambiguated only from honorific-titled aliases (reuses `api.extraction.normalization.gendered_title`); a character with no such alias is excluded from a gendered aggregation rather than risk stating the wrong gender as fact — this is what makes "What happens to Elizabeth's brother?" abstain instead of returning her sisters |
| SSE streaming (`ask`, `_event_stream`) | `api/routes/query.py` | **Built** (S6.5) — wraps `api/query/pipeline.py::answer_question`; narrative tokens are buffered until grounding completes rather than streamed live, so a sentence grounding would drop never reaches the user in the first place |
| Conversation memory (`resolve_conversation`, `carry_context`, `record_turn`, `set_scope`) | `api/query/conversation.py` | **Built** (S6.6) — context is token-budgeted, not turn-count-capped; a turn pushed out of budget is named in a one-line summary built from its own `resolved_names`, no second LLM call |
| `resolve_names` (name/nickname/partial/fuzzy/relative cascade, ranked candidates) | `api/extraction/resolution.py` | **Built** (S6.7) — reuses `api/extraction/normalization.py`; never an LLM call |
| `locate_quote` (exact → whitespace-normalised → fuzzy span match, `None` if unlocated) | `api/pipeline/quotes.py` | **Built** (S6.8) — reuses `local_copy` from `api/pipeline/render.py` |
| `QueryTimer` (per-stage timing, `as_dict()` → `QueryLog.latency_ms`) | `api/pipeline/timing.py` | **Built** (S6.9) — `api/query/pipeline.py` owns calling `.stage()`/`.mark_ttft()` and persisting the row |
| Spoiler enforcement | query layer, all surfaces | S8 |

## Route classes (Built, S6)

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

## SSE contract (Built, S6)

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

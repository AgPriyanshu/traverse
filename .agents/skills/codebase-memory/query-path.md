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
| `ReadingScope`, spoiler enforcement | `api/query/scope.py`, all graph/query/retrieval surfaces | **Built** (S8.1) — see below |

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

## Spoiler scoping — `ReadingScope` (Built, S8.1)

`ReadingScope` (`api/query/scope.py`) — a frozen `(book_order, chapter)`
dataclass — replaced the old pair of independently optional
`limit_book_order`/`limit_chapter` keyword arguments (each defaulting to
`None`) across the entire graph/query/retrieval layer. The pair still exists
at the HTTP boundary (`Query(default=None)` on every route, since "no limit"
is a legitimate reader choice — a finished book, or an admin view), but every
internal function below that boundary takes `scope: ReadingScope` with **no
default** — a call site that forgets it is a `TypeError`, not a silent
unfiltered read. `ReadingScope.unlimited()` makes "no limit" an explicit,
named choice (used by `api/review/**`, which is a reviewer-facing surface and
deliberately never spoiler-scoped).

**The real bug this closed:** before S8.1, `limit_book_order`/`limit_chapter`
were only plumbed through the *character* read paths (`get_character`,
`list_mentions`, `list_appearances`, `list_characters`, `get_graph`) and
retrieval (`dense_search`/`lexical_search`, already safe since S2). The
*relationship* read paths — `relations_out`, `relation_arc`, `shortest_path`,
`get_neighbourhood`, `list_evidence`, and the `relationship_lookup`/
`aggregation` Cypher templates — had **no reading-position parameter at all**,
so `api/query/pipeline.py`'s RELATIONSHIP_LOOKUP/PATH/AGGREGATION/SERIES_ARC
routes returned the whole project's relationship graph regardless of the
reader's position. A second, subtler leak: Neo4j's `RELATED` edge carries a
denormalised `page_refs` property written from **every** evidence row at
projection time (`graph/upsert.py`) — an edge that is itself correctly
visible can still cite a page from a *later* reassertion of it, so
`graph_repository.page_refs_for_relations` (used by `relations_out` and,
post-fetch, by `get_graph`/`get_neighbourhood`) re-trims pages from Postgres
even when the Neo4j-side edge visibility check already passed.

Enforced in three places, all of which must hold:

1. **graph** — every Neo4j template/query takes `$lbo`/`$lch` and filters on
   `(first_book_order, first_chapter)`: `graph/queries.py` (`get_graph`,
   `get_neighbourhood`, `shortest_path`, via the shared `_VISIBLE` fragment)
   and `query/templates.py` (`relationship_lookup`, `aggregation`, via
   `_LBO_LCH_VISIBLE`, a separate but semantically identical fragment — kept
   unshared across the two packages on purpose). Postgres-side hydration
   (`graph_repository.relations_out`/`relation_arc`/`list_evidence`) re-checks
   the same thing, since it is the source of truth and the one place that also
   trims per-evidence pages, not just whole edges.
2. **retrieval** — `retrieval/repository.py`'s `dense_search`/`lexical_search`
   and `retrieval/hybrid.py::hybrid_search` all take `scope` (no default);
   `query/retrieval.py::retrieve_for_narrative` threads it through.
3. **generation** — the five graph-derived classes render only from
   already-filtered `RelationOut`/`CharacterDetailOut` objects; `narrative`
   only ever sees `retrieve_for_narrative`'s filtered chunks. Aggregation's
   own answer *sentence* is a fourth, easy-to-miss surface: it must derive
   `other_names` from the post-filter `relations` list
   (`api/query/pipeline.py::_run_aggregation`), never from the raw Cypher
   `other_id` rows — those are unfiltered, and naming from them independently
   of `relations` reintroduces the leak even after `relations` itself is
   correctly filtered.

Name resolution is spoiler-filtered too: `pipeline.py::_resolve_phrase` drops
any `resolve_names` candidate not yet visible at `scope` *before* the
ambiguity check runs — a clarifying question ("Which Catherine do you mean?")
listing a not-yet-introduced character would itself be a leak.

**Known residual gap:** `conversation.py`'s carried `scope_book_id`/
`scope_chapter` (set by `set_scope` after a turn with an explicit reading
position) is never read back as a fallback when a later turn in the same
thread omits `limit_book_order`/`limit_chapter` — that turn runs fully
unscoped rather than inheriting the conversation's last position. Not fixed in
S8.1 (fe1's chapter slider, S8.6, is expected to always send both on every
request); flagged here rather than silently relied upon.

Measured **zero** leakage, `api/tests/query/test_spoiler_leakage.py` — 22
checks across every surface above (roster, character detail, whole-project
graph including denormalised `page_refs`, neighbourhood, shortest path,
relationship-lookup and aggregation templates, relation arc, evidence, dense
and lexical retrieval), each anchored around a synthetic corpus with content
strictly before and after the checkpoint. Run it after touching any surface
in this section.

## Related

[character-graph.md](character-graph.md) · [llm-runtime.md](llm-runtime.md) ·
[.agents/rules/graph-query.md](../../rules/graph-query.md) ·
[plans/sprint-6/](../../../plans/sprint-6/) · [plans/sprint-8/](../../../plans/sprint-8/)

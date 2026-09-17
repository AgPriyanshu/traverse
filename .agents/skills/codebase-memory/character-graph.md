# Characters & relationship graph

Roster discovery, alias resolution, relation extraction, Neo4j projection.
Symbols over line numbers.

## Key symbols

| Symbol | Location | Status |
| --- | --- | --- |
| `graph_db_session`, `create_nodes` | `api/db/graph_db.py` | Stub — `create_nodes` raises `NotImplementedError`; credentials still hardcoded. Replaced by `api/graph/client.py` in S1.4 |
| Neo4j `AsyncDriver` singleton, `healthcheck`, `graph.reset(book_id)` | `api/graph/client.py` | S1 |
| Ontology (`Predicate`, `family_of`, `inverse_of`, `is_symmetric`, `is_legal_transition`, `prompt_fragment`) | `api/graph/ontology.py` + `ontology.yaml` | S1 |
| `pipeline.extract_characters` (pass 1) | `api/extraction/` | S3 |
| Alias cascade, `honorifics.yaml`, nickname tables | `api/extraction/` | S3 |
| `cluster_contexts` (embedding similarity) | `api/graph/` | S3 |
| Merge / split endpoints | `api/routes/characters.py` | S3 |
| `relations.extract` (pass 2) | `api/relations/` | S4 |
| `pipeline.reconcile_characters` | `api/reconcile/` | S5 |
| Cross-book blocking (death, namesake, kinship) | `api/reconcile/` | S5 |
| Appearance recompute, order independence | `api/reconcile/` | S5 |
| Series-position validity, `/relations/arc` | `api/graph/` | S5 |
| Off-roster validator, quote-substring check | `api/relations/` | S4 |
| `relations.aggregate` | `api/relations/` | S4 |
| `graph.upsert` | `api/graph/` | S4 |

## Alias resolution cascade (S3)

Cheapest first; each stage sees only what the previous could not resolve:

1. exact / normalised
2. honorific + name-order stripping (`Mr.`, `Miss`, `-san`, `Tokita Kazu` ≡ `Kazu Tokita`) — **table-driven in YAML**, not inline regex
3. nickname / diminutive tables (Elizabeth → Lizzy/Eliza/Bess)
4. contextual embedding similarity over mention contexts
5. LLM adjudication on the residue only, batched

Each cluster records `resolution_method`, so the retro can report which stage
earned its cost. If stage 5 sees thousands of pairs, stages 1–4 are
underperforming — that is the finding, not a scaling problem.

## Name collision — the headline correctness case

Two characters can share a name (Catherine Earnshaw / Catherine Linton). String
evidence says merge; the truth is split. A merge is **blocked** by:

- co-presence as distinct participants in one scene
- generational markers ("young Catherine", "the elder")
- contradictory kinship (one is the other's mother)
- disjoint lifespans

On contradiction: keep separate, set `collision_suspected`, queue a
`merge_characters` review task. Canonical names must disambiguate —
`Catherine Earnshaw`, not `Catherine (2)`.

`test_wuthering_heights_two_catherines` is a permanent regression test.

## Series: reconciliation (S5)

**Characters and relations are project-scoped, not book-scoped.** Within-book
alias clustering (above) answers "are these two surface forms the same person in
this book?"; reconciliation answers "is this book's character the one the project
already knows?". Same cascade, different blocking evidence:

| Within a book | Across books |
| --- | --- |
| co-presence in a scene proves two names are different people | that signal does not exist |
| — | **death established in an earlier book** — flashback, namesake, or resurrection; never auto-link |
| — | contradictory kinship across volumes |
| generational namesake | generational namesake, at greater distance |

**The governing asymmetry:** a duplicate is visible and recoverable; a false
merge is silent and destructive. Bias tight, route the middle band to review
(`merge_across_books`), and report false merges as their own metric rather than
inside an F1.

Derived character fields (`first_book_id`, series-wide tier, mention count) are
**recomputed from all appearances** after every reconcile, never accumulated.
That is what makes out-of-order ingestion self-correct — uploading book 3 then
book 1 must produce a checksum-identical graph.

Reconciliation takes a **per-project lock**: two books reconciling concurrently
against the same roster create duplicate characters, and the bug only appears
under load.

## Pass 2 and prefix caching

Prompt structure — the **stable prefix must be byte-identical across every call
for a book** or vLLM's prefix cache misses and cost roughly doubles with no error:

```
[STABLE PREFIX]  ontology.prompt_fragment() + roster (sorted deterministically)
                 + extraction rules + few-shot examples
[VARIABLE]       chapter N · pages X–Y + chunk text
```

Sort the roster deterministically. A dict-ordering change breaks this silently.
Target ≥80% cache hit rate; it is alerted on in the ops dashboard.

**In a series the roster is the project's, not the book's** (S5) — that is what
lets book 5 state a fact about a book-1 character. The roster therefore grows with
the series, and the tier-filtered roster (protagonist + major always; minor only
when present in this book or chapter) stops being an optimisation. The prefix
must be byte-identical per **book**, not per project, since each book's tier
filter differs.

## Edge rules

- **No edge without evidence.** `graph.upsert` *raises*; it does not skip.
- **Aggregate before writing:** one edge with N evidence items. Group by
  `(subject, predicate, object)` **after inverse normalisation** — `child_of`
  one way and `parent_of` the other are the same fact. Canonicalise symmetric
  predicates by sorting the pair.
- **Materialise inverse edges** on upsert so traversal never depends on
  extraction direction.
- **Temporal change closes, never overwrites** — set `last_book_order`/
  `last_chapter`, `status='superseded'`, open a new edge. The history is the
  interesting part, and across a series it is the story.
- **Validity is series position** `(book_order, chapter)`, compared with SQL row
  comparison. A standalone book is `(1, chapter)` — one code path, no branch on
  project kind anywhere.
- **Aggregation is project-wide.** The same predicate reasserted in a later book
  extends the evidence set; a *different* predicate supersedes. Every evidence
  row carries `book_id` — "page 214" of which volume is not a citation.
- **Assertion provenance:** `narrated` / `dialogue` / `inferred`, with
  `asserted_by` for dialogue. Evidence that is only dialogue sets `hearsay`, and
  answers must attribute it rather than state it as fact.
- **Non-temporal contradictions** go to `resolve_conflict` review, never a
  confidence tiebreak.
- Confidence is computed from evidence count, agreement, and per-item
  confidence — **never a model self-report**.

## Neo4j shape

```cypher
(:Character {id, project_id, canonical_name, importance_tier,
             first_book_order, first_chapter, appears_in_books: [1,2,5]})
(:Character)-[:RELATED {predicate, family, confidence, status, assertion_type,
                        hearsay, evidence_count, page_refs, book_refs,
                        first_book_order, first_chapter,
                        last_book_order, last_chapter}]->(:Character)
```

`page_refs` is denormalised so a traversal answers "which pages" without a
Postgres round trip; full quotes hydrate on click. Batch writes with `UNWIND` —
one Cypher per edge on a 900-edge graph is minutes of round trips.

Neo4j Community supports **one database**. BE2 has exclusive write access during
sprints; `graph.reset(book_id)` exists from S1 so integration can rebuild.

## Related

[data-model.md](data-model.md) · [query-path.md](query-path.md) ·
[.agents/rules/graph-query.md](../../rules/graph-query.md) ·
[plans/sprint-3/](../../../plans/sprint-3/) · [plans/sprint-4/](../../../plans/sprint-4/)

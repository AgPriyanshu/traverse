# Characters & relationship graph

Roster discovery, alias resolution, relation extraction, Neo4j projection.
Symbols over line numbers.

## Key symbols

| Symbol | Location | Status |
| --- | --- | --- |
| Neo4j `AsyncDriver` singleton, `connect`, `close`, `session`, `execute`, `apply_schema`, `healthcheck` | `api/graph/client.py` | **Built** — `api/db/graph_db.py` is gone |
| `reset(book_id)`, `reset_project(project_id)` | `api/graph/projection.py` | **Built** |
| Ontology (`load`, `Ontology`, `Predicate`, `family_of`, `inverse_of`, `is_symmetric`, `is_extracted`, `is_legal_transition`, `prompt_fragment`, `to_contract`) | `api/graph/ontology.py` + `ontology.yaml` | **Built** |
| Roster and graph reads (`project_exists`, `list_characters`, `get_character`, `get_graph`, `list_mentions`) | `api/graph/repository.py` | **Built** — Postgres-backed; S4.7 moves `get_graph` to Neo4j. `get_character`/`list_mentions` are `limit_book_order`/`limit_chapter`-aware (S3.6); `get_character` also returns `alias_detail`, `attributes` and a one-query `mentions_per_chapter` histogram |
| `pipeline.extract_characters` (pass 1, S3.1), non-character rejection (S3.2) | `api/extraction/discovery.py`, `api/extraction/rejection.py` | **Built** |
| Alias cascade (S3.3), `honorifics.yaml`, `nicknames.yaml` | `api/extraction/aliases.py`, `api/extraction/normalization.py` | **Built** |
| Name-collision guard (S3.4) | `api/extraction/collision.py` | **Built** |
| Character records, tiering, attributes (S3.5) | `api/extraction/characters.py`, `tiering.py`, `attributes.py` | **Built** |
| `pipeline.resolve_aliases` task body (clusters → `Character`/`CharacterAppearance`/`CharacterMention`, idempotent replace) | `api/pipeline/tasks.py`, `api/extraction/repository.py` | **Built** |
| `cluster_contexts`, `MentionContext`, `similarity_threshold` (embedding similarity, stage 4 of the cascade) | `api/graph/similarity.py` | **Built** (S3.8) — threshold measured against real BGE-M3 + real text, not assumed; see `plans/sprint-3/HANDOFF.md`. Reuses `retrieval/repository.py::embedding_model()`, never a second copy. `api/extraction/similarity.py` lazy-imports it (degraded no-op if unavailable) — both are now landed so the degradation path is dead code in practice, kept for the same defensive reason it was written |
| `merge_characters`, `split_character` (transactional, mention-accurate) | `api/graph/merge.py`, wired at `POST /characters/merge` and `POST /characters/{id}/split` | **Built** (S3.7) — both recompute appearances and derived fields from actual `CharacterMention` rows rather than adjusting counters, which is what makes a merge followed by a split restore the original partition |
| `relations.extract` (pass 2) | `api/relations/` | **Built** (S4; `extract.py`, `validator.py`, `aggregate.py`, `graph/upsert.py`, reads in `graph/queries.py`) |
| `pipeline.reconcile_characters` | `api/reconcile/` | S5 |
| Cross-book blocking (death, namesake, kinship) | `api/reconcile/` | S5 |
| Appearance recompute, order independence | `api/reconcile/` | S5 |
| Series-position validity, `/relations/arc` | `api/graph/` | S5 |
| Off-roster validator, quote-substring check | `api/relations/` | **Built** (S4; `extract.py`, `validator.py`, `aggregate.py`, `graph/upsert.py`, reads in `graph/queries.py`) |
| `relations.aggregate` | `api/relations/` | **Built** (S4; `extract.py`, `validator.py`, `aggregate.py`, `graph/upsert.py`, reads in `graph/queries.py`) |
| `graph.upsert` | `api/graph/` | **Built** (S4; `extract.py`, `validator.py`, `aggregate.py`, `graph/upsert.py`, reads in `graph/queries.py`) |
| `build_reading_chunks`, `candidate_reading_chunks` — scene-level pass-2 reading units | `api/relations/scenes.py`, `api/relations/inputs.py` | **Built** (S4.16) — see "Recall audit" below |

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

Stages 4/5 merge only **blocking pairs** (clusters sharing a stripped first or
last token) and loop each stage to a fixpoint — one pass only merges disjoint
pairs, so a name with several unresolved aliases (six ways to write
"Elizabeth Bennet") needs more than one round to fully consolidate.
`similarity.context_similarity` lazy-imports `api.graph.similarity` at call
time and returns `None` (stage 4 no-ops, nothing merges) if be2's S3.8 hasn't
landed in this checkout yet — safe to import at module scope, comes online
automatically once merged, nothing to change on this side.

Tiering method (`mention_count` | `participation`) is chosen by the
`TIERING_METHOD` env var, read directly in `tiering.py` rather than through
`api.config.settings` (orchestrator-owned, no such key yet — SCR filed in
`plans/sprint-3/SCR.md`).

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

## Recall audit (S4.16) — chunk granularity was the biggest lever

Sprint 4's real-run DoD check found precision near target (~93-100% hand
checked) but recall stuck at 0.33, unexplained by the roster bugs already
fixed. Funnel instrumentation on the live Pride and Prejudice book (719
chunks) found the root cause: median `documentchunk` length is **60
characters** (487 of 719 chunks are under 100 chars) — most "chunks" are one
clause, not a passage. Two consequences, both now addressed:

- **Prefilter under-read.** be1's S4.10 rule keeps a 1-mention chunk when its
  scene has 2+ participants, but only when the chunk's *own* mention count is
  >= 1 — a 0-mention pronoun clause ("he had the means of exercising it") is
  dropped even inside an otherwise-qualifying scene. Measured: 48 such chunks
  on this book. `build_reading_chunks` (`api/relations/scenes.py`) merges each
  scene's member chunks into one reading unit before candidate selection,
  recovering them; falls back to the old per-chunk rule when scene tables
  aren't migrated in. Raised chunks read 231 -> 279 (+21%) on the live book.
- **Validator over-rejected the quote, not the chunk.** `ENDPOINT_NOT_IN_CHUNK`
  checks the whole grounding text (chunk or, now, scene) for both names, but a
  separate check required the cited *quote itself* to name at least one
  endpoint — rejecting a real relation stated as "she refused him" even when
  both names are established two sentences earlier in the same reading unit.
  Removed (`QUOTE_NAMES_NEITHER` in `api/relations/validator.py`); the
  companion check (`QUOTE_NAMES_OTHERS`, a quote naming only *other* roster
  characters) is unchanged and still catches Sprint 3's wrong-pair-quote
  finding. The second-pass verifier (`verify.py`) already re-grades every
  accepted quote against its claim alone and fails closed, so it is the
  backstop for "does this pronoun resolve to this pair", not a mechanical
  substring check.

Same-session controlled A/B on the live book (73-character roster, same
vLLM instance, `/ops/relation-quality`):

| | before (chunk-level, old validator) | scene-merge only | scene-merge + validator fix |
|---|---|---|---|
| precision | 1.0 | 0.8 | 0.71 |
| recall | 0.242 | 0.242 | 0.303 |
| f1 | 0.390 | 0.373 | 0.426 |

Recall moved but is nowhere near the 0.80 DoD target even after both fixes —
predicates requiring an indirect/ironic cue (`enemy_of`, `rival_of`,
`unrequited_love_for`, `deceives`) or a transitive inference the text never
states in one place (`in_law_of` derived from two marriages) stayed at zero
true positives in every run. Full numbers, the funnel breakdown by rejection
reason, and the trade-off discussion are in `plans/sprint-4/HANDOFF.md`.
**Run-to-run LLM sampling variance is real and roughly the same size as these
deltas** (a from-scratch re-run of the unmodified code, same book, measured
0.333 in one session and 0.242 in this one) — treat any single number here as
directional, not exact, until Sprint 8's calibration work adds repeated-run
averaging.

## Neo4j shape

```cypher
(:Book      {id, project_id, series_order, title})
(:Character {id, project_id, canonical_name, importance_tier, mention_count,
             first_book_order, first_chapter, appears_in_books: [1,2,5]})
(:Character)-[:APPEARS_IN {book_id, first_page, first_chapter,
                           mention_count, tier}]->(:Book)
(:Character)-[:RELATED {id, predicate, family, confidence, status, assertion_type,
                        hearsay, evidence_count, page_refs, book_refs,
                        first_book_order, first_chapter,
                        last_book_order, last_chapter}]->(:Character)
```

**The projection is book-attributed, and that is load-bearing.** Characters and
relations are project-scoped, so "delete what this book contributed" is only
answerable if provenance is on the node and the edge: `APPEARS_IN` per book,
`book_refs` (book UUIDs as strings) per edge. Without it, re-ingesting one
volume of a series means dropping the whole project's graph.

`page_refs` entries are `"<book_order>:<page>"` strings, not bare ints — in a
series a page number without its volume is not a citation, and `reset` needs to
drop one book's pages without touching another's. **The API contract now
matches** (SCR-5, landed at the Sprint 2 freeze): `GraphEdgeOut.page_refs` and
`RelationOut.page_refs` are `list[PageRefOut]` (`{book_order, book_id, page}`),
not bare ints — the hydration parses the `"<order>:<page>"` string and resolves
`book_id` from it rather than discarding the book on the way out.

`page_refs` is denormalised so a traversal answers "which pages" without a
Postgres round trip; full quotes hydrate on click. Batch writes with `UNWIND` —
one Cypher per edge on a 900-edge graph is minutes of round trips.

### `reset(book_id)` — Built, S1

Neo4j Community supports **one database**. BE2 has exclusive write access during
sprints; `reset` exists from S1 so integration can rebuild from Postgres.

- Edges whose `book_refs` name **only** this book are deleted.
- Edges shared with another volume are **trimmed, not deleted**: the book is
  removed from `book_refs`, its `page_refs` are dropped, and `stale = true` is
  set. **S4's `graph.upsert` must clear `stale` and recompute `evidence_count`
  and `confidence` from Postgres** — Neo4j cannot recompute them itself.
- `APPEARS_IN` edges to the book go, then characters left with no appearance are
  `DETACH DELETE`d. A character who also appears elsewhere survives with the
  book's `series_order` removed from `appears_in_books`.
- `reset_project(project_id)` drops a whole project for a full rebuild.

### LangGraph checkpointer — Built, S1

`api/graph/checkpoint.py` — `checkpointer()` and `setup_checkpointer()` wrap
`AsyncPostgresSaver` against the **application** database, so a review task row
and the paused run it belongs to commit together. `connection_string()` strips
SQLAlchemy's `+psycopg` suffix, which psycopg refuses.

**A SIGKILLed process resumes from its checkpoint with state intact** —
verified by `api/tests/graph/test_checkpointer.py`, which spawns a real
subprocess, kills it at the interrupt, and resumes from a fresh one. This is
PRD F5.1's acceptance criterion and the whole of Sprint 7 rests on it; do not
weaken that test into an in-process cancellation.

## Related

[data-model.md](data-model.md) · [query-path.md](query-path.md) ·
[.agents/rules/graph-query.md](../../rules/graph-query.md) ·
[plans/sprint-3/](../../../plans/sprint-3/) · [plans/sprint-4/](../../../plans/sprint-4/)

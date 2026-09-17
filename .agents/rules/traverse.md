---
description: Traverse architecture, pipeline shape, stores, and the invariants that make citations trustworthy
scope: always
---

# Traverse

Upload a novel PDF; get a character knowledge graph where every relationship is
click-through to the pages that prove it.

**See also:** [traverse-prd.md](../../traverse-prd.md) (product spec),
[AGENTS.md](../../AGENTS.md) (style), [BRANCH.md](../../BRANCH.md) (ownership),
[codebase-memory](../skills/codebase-memory/SKILL.md) (where code lives).

## Projects and series

**A project is the unit of identity; a book is the unit of ingestion.** A
standalone novel is a one-book project — there is no second code path anywhere.

- `character` and `relation` are **project-scoped**. One Harry Potter, not seven.
- `character_appearance` (character × book) is the append target: ingesting book
  five adds an appearance, not a duplicate character.
- Relationship validity is **series position** `(book_order, chapter)`. A
  standalone is `(1, chapter)`.
- **Ingestion is order-independent.** Derived character fields are recomputed
  from all appearances after every reconcile, never accumulated, so uploading
  book 3 before book 1 self-corrects.
- Reconciliation takes a **per-project lock**; concurrent reconciles against one
  roster create duplicates.

## Shape

```
PDF → Docling parse → chapter segmentation → chunk (page provenance)
    → embed (BGE-M3 → pgvector)
    → pass 1: character discovery → alias clustering → book roster
    → reconcile against the PROJECT roster → appearances + recompute
    → pass 2: roster-informed relation extraction → aggregate → Neo4j projection
    → query: route → graph-constrain → retrieve → generate → ground → cite
```

Ingestion is a Celery chain of independently-retryable stages. The stages that
can *pause for a human* (alias resolution, relation aggregation) run as a
LangGraph flow with the Postgres checkpointer. Parsing and embedding do not —
they contain no decisions and checkpointing a 1,100-chunk payload is expensive.

## Stores and their roles

| Store | Holds | Rule |
| --- | --- | --- |
| Postgres + pgvector | books, chapters, chunks, embeddings, characters, mentions, relations, evidence, review tasks, logs | **Source of truth** |
| Neo4j | Character nodes, `RELATED` edges with denormalised `page_refs` | **Rebuildable projection.** Never holds a fact Postgres does not. |
| MinIO | source PDFs, rendered page PNGs | Page renders are a cache; they regenerate |
| Langfuse | traces, token accounting | Every LLM call, tagged `purpose` + `book_id` |

`make graph-rebuild BOOK=<id>` wipes and re-projects Neo4j. A corrupted graph is
a five-minute rebuild, never a data-loss incident — keep it that way.

## Non-negotiable invariants

Relaxing any of these to make a test pass breaks the product's central claim.

- **Page provenance is mandatory.** Every chunk carries `pages[]`,
  `page_start`, `page_end`. Nothing downstream may exist without tracing to a page.
- **No edge without evidence.** `graph.upsert` *raises* on an edge with zero
  evidence items — it does not skip it.
- **Quotes must be locatable.** A quote that cannot be found in its cited chunk
  is fabricated evidence; drop the citation rather than cite a page you cannot
  point at.
- **Off-roster names are invention.** Relation subjects and objects must match a
  known `Character.canonical_name` or alias.
- **Human-verified wins.** A re-run that disagrees raises a review task; it never
  overwrites.
- **Temporal change closes, never overwrites.** `friend_of` → `enemy_of` opens a
  new edge and closes the old one with `last_chapter`.
- **Spoiler scope is enforced at the query layer** — graph, retrieval, and
  generation — never by instructing the model.

## Two-pass extraction

The project's central architectural bet ([PRD §5.2](../../traverse-prd.md)).
Pass 1 finds the cast; pass 2 re-reads with the roster in the prompt **prefix**
so pronouns resolve against a known cast and the model cannot invent characters.

Cost depends on vLLM prefix caching, which requires the roster block to be
**byte-identical across every call for a book**. Sort the roster deterministically.
A dict-ordering change breaks the cache silently and doubles the bill with no error.

## Boundaries

- Services, repositories, and pipeline code must **not** import from `api/routes/`.
- All model calls go through `api/llm` — never instantiate a chat model elsewhere.
- All DB access goes through a repository module, not inline queries in views or
  tasks.
- The frontend never talks to Neo4j or Postgres; it talks to the API.

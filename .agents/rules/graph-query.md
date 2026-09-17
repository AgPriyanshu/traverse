---
description: Graph, relation, and query-layer patterns — evidence, Cypher safety, retrieval order
scope: paths
paths: api/graph/**/*.py, api/relations/**/*.py, api/query/**/*.py, api/retrieval/**/*.py
---

# Graph & query

**See also:** [AGENTS.md](../../AGENTS.md),
[character-graph.md](../skills/codebase-memory/character-graph.md),
[query-path.md](../skills/codebase-memory/query-path.md).

## Must

- **Templated Cypher only.** The LLM selects a template ID and fills named slots;
  it never emits Cypher. Validate slots against the ontology before execution.
- Ontology lives in `api/graph/ontology.yaml` — predicates, families, inverses,
  symmetry, legal transitions. Adding a predicate is a YAML change, and the
  extraction prompt renders from the same source so prompt and validator cannot
  drift.
- Materialise inverse edges on upsert so traversal never depends on which
  direction the extractor happened to write. Canonicalise symmetric predicates by
  sorting the pair.
- Aggregate before writing: one edge with N evidence items, not N edges.
- Retrieval order is **graph first**: resolve names → node/edge evidence →
  hybrid search within that set → whole-book vector search only as last resort.
  Log which tier answered; the ablation table needs the breakdown.
- Batch Neo4j writes with `UNWIND`. One Cypher per edge on a 900-edge graph is
  minutes of round trips.
- Cap `max_hops` on path queries at 4.
- `chapter_lte` is a **required field** on the query context object, not an
  optional argument. `None` meaning "no limit" must be an explicit choice at the
  call site — optional spoiler filters get forgotten on exactly one code path.

## Must not

- Write an edge with no evidence. The guard raises; do not add a bypass.
- Resolve a genuine contradiction by confidence tiebreak. Non-temporal conflicts
  go to `resolve_conflict` review.
- Overwrite an edge on a temporal change. Close it and open a new one.
- Construct a Neo4j driver per call. Use the singleton in `api/graph/client.py`.
- Present a dialogue-sourced (`hearsay`) edge as narrative fact. Attribute it.

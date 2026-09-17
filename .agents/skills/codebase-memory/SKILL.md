---
name: codebase-memory
description: >-
  On-demand map of the Traverse codebase: data model, ingestion pipeline,
  character/alias resolution, relationship graph, query and citation path, LLM
  runtime, web app, and infra topology. Use instead of explore subagents when
  working on Docling parsing, chunking, chapter segmentation, page provenance,
  BGE-M3 embeddings, pgvector, character extraction, alias clustering, relation
  extraction, evidence, Neo4j upsert, ontology predicates, query routing,
  templated Cypher, citations, spoiler scoping, review tasks, Celery stages,
  vLLM prefix caching, token budgeting, compose services, or the React app.
---

# Codebase memory

Read-only maps of Traverse so agents can skip broad exploration. Treat these as
a **routing index**, not source of truth.

## Why this exists

Four agents work in parallel worktrees on one codebase. A broad explore pass
costs tens of thousands of tokens per agent per session and returns a worse
answer than a 90-line map written by whoever built the subsystem. Multiply that
by four agents and eight sprints and it is the single largest avoidable cost in
the project.

## How to use

1. Match the task to a topic in the table below.
2. Read **only** that file (one level deep from this skill).
3. Confirm any symbol you will edit with a targeted `Grep` / `Read` before
   changing code.
4. If a gap remains after the map plus a symbol check, then explore — narrowly.
5. **If the map is wrong, correct it in the same change that fixes the code.**

Do **not** launch explore or general-purpose subagents for these areas until the
matching memory file plus a quick symbol check still leave a gap.

## Topic → file

| Topic | Triggers | File |
| ----- | -------- | ---- |
| Tables, keys, constraints | any model, migration, `human_verified`, `content_hash`, evidence rows, what column exists | [data-model.md](data-model.md) |
| Parse → chunk → embed | Docling, `HybridChunker`, `DocumentChunker`, chapter detection, `CHAPTER_RE`, page provenance, `pages[]`, BGE-M3, upload, Celery stages, retry, dead-letter | [ingestion-pipeline.md](ingestion-pipeline.md) |
| Characters, aliases, relations, graph | pass 1, pass 2, roster, alias clustering, B³, name collision, ontology, predicates, inverses, evidence, temporal validity, Neo4j upsert, `graph.reset` | [character-graph.md](character-graph.md) |
| Answering and citing | query router, templated Cypher, hybrid retrieval, RRF, rerank, grounding, abstention, SSE events, `chapter_lte`, spoiler scope, `PageRef` | [query-path.md](query-path.md) |
| Model calls | `api/llm`, `structured_call`, `purpose`, routing policy, `plan_batches`, token budget, vLLM, prefix caching, Langfuse tags, transient vs permanent errors | [llm-runtime.md](llm-runtime.md) |
| Frontend | routes, `schema.d.ts`, query hooks, page viewer, graph explorer, review queue, tokens, Chakra | [web-app.md](web-app.md) |
| Running it | compose services, ports, profiles, `make` targets, per-agent DB isolation, healthchecks, CI, model cache | [infra-topology.md](infra-topology.md) |

## Reading the status column

Most of this codebase is planned, not written. Every map marks each symbol:

| Mark | Meaning |
| --- | --- |
| **Built** | Exists now. Grep it. |
| **S*n*** | Lands in sprint *n* ([plans/](../../../plans/)). **Do not grep for it — it is not there.** Read the sprint plan instead. |
| **Broken** | Exists but does not work. Named explicitly so you do not debug a known defect. |

This column is the highest-value part of these files. An agent that greps for
`ReviewTask` in sprint 2 burns a minute and learns nothing; the map says
"S7" and points at the plan.

## Verify / refresh protocol

- Anchor claims on **symbol names** (`DocumentChunker.generate_chunks`,
  `_prepare_chapters`), never line numbers.
- Record **invariants and gotchas**, not pasted snippets. If a map starts
  quoting code, it has become a worse copy of the code.
- Keep each file under ~120 lines. A map nobody reads in full is not a map.
- After a change that alters the schema, a stage boundary, an ontology
  predicate, an SSE event, or a service topology, update the matching file **in
  the same commit**. This is in the sprint Definition of Done
  ([BRANCH.md](../../../BRANCH.md) §10).
- When a sprint lands, flip its entries from **S*n*** to **Built**. That is part
  of the merge train, not a follow-up.

## Related

- Coding style: [AGENTS.md](../../../AGENTS.md), [api/AGENTS.md](../../../api/AGENTS.md), [web/AGENTS.md](../../../web/AGENTS.md)
- Ownership, branches, merge train: [BRANCH.md](../../../BRANCH.md)
- Architecture rules: [.agents/rules/](../../rules/)
- Product spec: [traverse-prd.md](../../../traverse-prd.md)
- Sprint plans: [plans/](../../../plans/)

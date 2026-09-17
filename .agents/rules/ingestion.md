---
description: Ingestion and character-extraction patterns — stages, provenance, batching, idempotency
scope: paths
paths: api/pipeline/**/*.py, api/extraction/**/*.py, api/workers/**/*.py
---

# Ingestion & extraction

**See also:** [AGENTS.md](../../AGENTS.md),
[ingestion-pipeline.md](../skills/codebase-memory/ingestion-pipeline.md) (symbol map).

## Must

- Every stage is independently retryable and **resumable**. A failure in
  extraction must not discard the parse, chunks, or embeddings. Process only
  rows that still need work (`WHERE text_embedding IS NULL`), so a restart
  resumes mid-book.
- Classify errors: a transient network fault retries with backoff; a malformed
  PDF is **permanent** and must not retry four times.
- Re-running a stage is idempotent — delete this book's rows for that stage
  first, do not append.
- Batch LLM work with `api.llm.budget.plan_batches` against the model's own
  tokenizer. Never a fixed chunk count; prose token density varies enough that
  fixed batching either wastes context or overflows it.
- Pass 1 optimises **recall**; precision is recovered by rejection and alias
  clustering. A character missed in pass 1 does not exist downstream.
- Store every rejection with its reason. A silently dropped candidate is
  unrecoverable and invisible to the eval harness.
- Content-hash idempotency: handle `IntegrityError` on the unique constraint
  rather than check-then-insert.

## Must not

- Buffer a whole PDF in memory. Stream to MinIO and hash while streaming.
- Default a missing page number to `0`. An empty `pages[]` is a bug to surface,
  not a null to paper over.
- Merge two characters on string evidence when context contradicts it —
  co-presence in a scene, generational markers, contradictory kinship, or
  disjoint lifespans all block a merge and route it to review. Over-merging is
  the failure mode the PRD calls "catastrophic and silent".
- Load a second copy of the embedding model. Reuse the process-scope handle.

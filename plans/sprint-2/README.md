# Sprint 2 — Ingestion Pipeline

**Goal:** upload a real novel PDF and watch every stage complete, ending with
chapters, chunks, and embeddings in Postgres — each chunk carrying page
provenance you can click through to the rendered page.

**PRD refs:** F1.1 – F1.5 · NFR-rel · Phase 1, 1.5

**Ownership amendment (permanent from this sprint):** `api/llm/**` is owned by
**be2**. It becomes the shared LLM substrate — client, structured output,
retries, routing, and the token-budget batcher that be1 needs in Sprint 3. be1
imports it and never edits it.

---

## Contract freeze (Day 1)

| Item | Detail |
|---|---|
| Migration `0007` | `book.storage_key`, `book.content_hash` unique, `ingestion_run` + `ingestion_stage` tables, `document_chunk.tsv` generated column + GIN index, `chapter.detection_method` |
| `contracts/pipeline.py` | `IngestionRunOut`, `StageStatus` finalised, `DeadLetterOut` |
| `contracts/llm.py` | `LLMRequest`, `StructuredCall`, `TokenBudget`, `BatchPlan` — **be2 produces, be1 consumes in Sprint 3** |
| `contracts/api.py` | `PageRenderOut` (image URL, width, height, text spans), `ChunkOut` with `page_start`/`page_end`/`chapter_number` |
| Route stubs | `POST /api/books`, `GET /api/books/{id}/pages/{n}`, `GET /api/books/{id}/chunks`, `POST /api/books/{id}/reprocess`, `GET /api/search` |

---

## Scope

| Story | Owner | Summary |
|---|---|---|
| S2.1 | be1 | Real upload → MinIO, content-hash idempotency, book row, chain dispatch |
| S2.2 | be1 | `pipeline.parse_and_chunk` — Docling parse persisted with provenance |
| S2.3 | be1 | `pipeline.segment_chapters` — regex + LLM fallback, persisted with page ranges |
| S2.4 | be1 | `pipeline.embed_chunks` — batched BGE-M3, resumable |
| S2.5 | be1 | Stage retry, dead-letter, resume-from-last-good, `POST /reprocess` |
| S2.6 | be1 | Page render service — page N → PNG + text spans, cached in MinIO |
| S2.7 | be2 | `api/llm/` — client, structured output, retry, local/API routing |
| S2.8 | be2 | Token-budget batcher — the Sprint 3 dependency |
| S2.9 | be2 | Hybrid retrieval — pgvector + `ts_rank_cd` BM25 + RRF, `GET /api/search` |
| S2.10 | be2 | Cross-encoder reranker behind a flag, measured not assumed |
| S2.11 | fe1 | Upload flow — drag-drop, progress, error recovery |
| S2.12 | fe1 | Live ingestion progress — per-stage stepper, failure detail, retry button |
| S2.13 | fe1 | Chapters view + chunk inspector with page provenance |
| S2.14 | fe1 | Page viewer — PDF.js, page navigation, span highlight API ready for Sprint 6 |
| S2.15 | do1 | MinIO wiring, signed URLs, lifecycle rules |
| S2.16 | do1 | Corpus seeding — public-domain novels fetched, verified, licensed |
| S2.17 | do1 | Langfuse per-stage tracing + stage timing in `api/ops/` |
| S2.18 | do1 | Flower, dead-letter visibility, integration test harness in CI |

---

## Demo script (Day 5)

```bash
make up && make seed                      # 5 public-domain novels staged
open http://localhost:5174/books/upload
# drag Pride_and_Prejudice.pdf (≈430 pages)
```

1. Upload returns a book ID in **under 3 seconds** (F1.1) — page does not block.
2. The stepper shows parse → chapters → embed advancing live with durations.
3. Chapters view lists **61 chapters** with correct numbers, titles and page
   ranges; spot-check three against the PDF.
4. Chunk inspector shows a chunk, its chapter, and its page range; clicking it
   opens the page viewer at the right page.
5. Re-upload the same file → "already ingested", zero duplicate rows (F1.5).
6. `docker compose restart celery-worker` mid-embed → run resumes from the last
   completed stage, does not restart from parse (F1.2).
7. Corrupt a PDF, upload → book lands in dead-letter with the failing stage and
   error text; "Retry" re-runs just that stage.
8. `curl "localhost:8000/api/search?book_id=…&q=entailment"` returns ranked
   chunks with page numbers.

## Definition of Done

- [ ] End-to-end ingestion of a 430-page novel completes unattended
- [ ] Chapter boundary recall ≥ 95% on the seeded corpus, measured with a script
      committed to `api/tests/fixtures/chapter_truth/`
- [ ] Every chunk has non-null `page_start`, `page_end`, `pages[]` (F1.3) —
      enforced by a DB constraint, not a code convention
- [ ] Stage failure never destroys completed upstream work
- [ ] Ingestion wall clock recorded in `RETRO.md` against the ≤25 min target
- [ ] `RETRO.md` written

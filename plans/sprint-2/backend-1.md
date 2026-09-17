# Sprint 2 · Backend Engineer 1

**Branch:** `ai/be1/sprint-2-ingestion` · **Worktree:** `../traverse-wt/be1`

## Mission

Turn the chunker into a pipeline. By Friday a user drops a 430-page PDF into the
browser and, unattended, ends up with chapters, chunks, embeddings, and page
provenance in Postgres — with any single stage failure recoverable without
redoing the expensive ones.

## Owned paths

`api/pipeline/**`, `api/workers/**`, `api/routes/books.py`, `api/tests/pipeline/**`

New dependency: `api/llm/` is **be2's** from this sprint. You consume it.

---

## S2.1 — Upload

`POST /api/books`, multipart. Stream to MinIO — **never buffer a 200 MB PDF in
memory**; hash while streaming with `hashlib.blake2b`.

Order matters: hash → check `get_book_by_hash` → if found, return `200` with
`{"status": "already_ingested", "book_id": ...}` and **do not re-upload the
object** (F1.5). Otherwise store at `books/{book_id}/source.pdf`, create the
`Book` row with `status=queued`, dispatch `ingestion_chain(book_id)`, return
`202` with the ID.

Extract title/author from PDF metadata where present; fall back to filename.
Reject non-PDF at the boundary with a message naming what was received.

*Acceptance:* 200 MB upload returns in <3s (F1.1) and the API process RSS does
not grow by the file size. Concurrent identical uploads produce exactly one book
row — the `content_hash` unique constraint is the arbiter, so handle
`IntegrityError` rather than checking-then-inserting.

## S2.2 — `pipeline.parse_and_chunk`

Fetch from MinIO to a temp path, run the S1.2 chunker, persist via
`bulk_insert_chunks`. Set `book.page_count` from the Docling document.

**Page provenance is mandatory (F1.3).** A chunk arriving with an empty `pages[]`
is a bug, not a null — log the chunk, fail the stage, and let DO1's constraint
catch any that slip through. The current code silently defaults to `0`; remove
that fallback.

**Dialogue integrity (PRD §5.3):** prefer paragraph boundaries over hard token
limits where Docling gives you the choice. A split mid-exchange loses the
speaker and will cost you relation recall in Sprint 4.

*Acceptance:* 430-page novel yields ~1,100 chunks, every one with a valid page
range inside `[1, page_count]`. Re-running the stage is idempotent — it deletes
this book's chunks first, it does not append.

## S2.3 — `pipeline.segment_chapters`

Promote the existing `_prepare_chapters` / `_parse_chapter_heading` logic to its
own stage, persisting `Chapter` rows with `number`, `title`, `page_start`,
`page_end`, `heading_text`, `detection_method`, `confidence`.

Fix three real problems in the current implementation:

1. `_prepare_chapters` breaks after the first item per page (`if count >= 1:
   break`), so a chapter heading not first on its page is missed.
2. Chapter matching is by heading **text equality**, which collides when two
   chapters share a title.
3. Every ambiguous heading costs an LLM call — batch them through be2's
   `api/llm` structured-output helper instead of one call per heading.

`page_end` is the next chapter's `page_start - 1`; the last chapter runs to
`page_count`. Back-fill `document_chunk.chapter_id` after chapters exist.

*Acceptance:* ≥95% boundary recall and ≤2% false positives (F1.4) against
`api/tests/fixtures/chapter_truth/*.json` — hand-label the seeded corpus. This
number goes in the retro; it gates spoiler mode (F4.5) and edge validity (F3.3).

## S2.4 — `pipeline.embed_chunks`

Split from parsing so a parse survives an embedding failure. Batch by token
count, not row count. `normalize_embeddings=True` — the cosine-distance queries
assume unit vectors. Process only chunks where `text_embedding IS NULL` so a
restart resumes mid-book.

*Acceptance:* Killing the worker at 50% leaves 50% embedded; restart completes
the rest and re-embeds nothing.

## S2.5 — Retry, dead-letter, resume

- `autoretry_for=(TransientError,)` with backoff (F1.2). A malformed PDF is
  **permanent** — retrying it four times wastes 20 minutes; classify errors.
- `IngestionRun` + `IngestionStage` rows drive `GET /books/{id}/status`.
- Terminal failure → `book.status=failed`, stage row holds stage name, error
  class, message, truncated traceback.
- `POST /api/books/{id}/reprocess?from_stage=` re-runs from a named stage,
  preserving everything upstream and **all `human_verified` records** (F5.4 —
  build the guard now, it is cheap now and expensive to retrofit).

*Acceptance:* All eight failure injections in `api/tests/pipeline/test_failures.py`
leave the book recoverable, with upstream work intact.

## S2.6 — Page render service

`GET /api/books/{id}/pages/{n}` → `PageRenderOut`: a signed MinIO URL for a PNG
(150 DPI), page dimensions, and the text spans with their bounding boxes.

Render lazily on first request, cache at `books/{id}/pages/{n}.png`. A
1,000-page novel rendered eagerly is 400 MB of PNG nobody asked for.

The span payload is what Sprint 6's citation highlighting draws on — agree the
coordinate space with fe1 **on Day 2** (top-left origin, PDF points, unscaled)
and record it in `HANDOFF.md`. Getting this wrong is discovered in Sprint 6.

*Acceptance:* Cold request <2s, cached <200ms. Spans align with the rendered
image at 100% and 200% zoom.

---

## DoD

- [ ] Full ingestion unattended on the seeded corpus, wall clock recorded
- [ ] Chapter accuracy measured and written into `RETRO.md`
- [ ] Failure-injection suite green
- [ ] `HANDOFF.md`: page-span coordinate contract (fe1), chunk/chapter query
      shapes (be2 needs them for Sprint 4 pass-2 batching)

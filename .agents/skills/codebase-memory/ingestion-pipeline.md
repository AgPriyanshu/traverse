# Ingestion pipeline

PDF → chunks with page provenance. Symbols over line numbers — `Grep` before
editing.

## Key symbols

`api/document_pipeline/` is **gone** — it moved to `api/pipeline/` in S1.2. Do
not grep for it.

| Symbol | Location | Status |
| --- | --- | --- |
| `DocumentChunker` (`load_document`, `generate_chunks`, `detect_chapters`, `embed_texts`, `warm`) | `api/pipeline/chunking.py` | Built |
| `DocumentChunker._prepare_chapters` | same | Built — **has bugs, see below** |
| `DocumentChunker._parse_chapter_heading` | same | Built |
| `DocumentChunker._classify_chapter_heading` | same | Built — LLM fallback, opt-out via `llm_classify=False`; one call per heading, batch it (S2.3) |
| `resolve_device`, `_document_converter`, `_tokenizer`, `_embedding_model` | same | Built — process-scoped `lru_cache`, **not** per call |
| `CHAPTER_RE`, `CHUNK_MAX_TOKENS`, `ChapterInfoStructuredOutput` | `api/pipeline/constants.py` | Built |
| `_roman_to_int`, `_normalize_chapter_number` | `api/pipeline/chunking.py` | Built |
| `DocumentParseError`, `MissingProvenanceError` | `api/pipeline/errors.py` | Built — both `PermanentError` |
| `PageParseError` | same | Built — `TransientError`, see gotchas |
| `celery_app`, `STAGES`, `ingestion_chain()` | `api/tasks.py` | **Built — frozen, orchestrator-owned** |
| `TransientError` / `PermanentError`, `RETRY_POLICY` | `api/workers/errors.py`, `api/workers/policy.py` | Built — the retry contract for every agent's tasks |
| `stage()`, `StageRecord`, `open_run`, `finish_run` | `api/workers/stages.py` | Built |
| `celery_app` re-export, `import_task_modules`, `missing_stage_tasks`, `warm_models` | `api/workers/app.py` | Built — worker entry point |
| repository (`create_book`, `get_book_by_hash`, `bulk_insert_chunks`, `upsert_chapters`, `set_book_status`, `get_stage_statuses`) | `api/pipeline/repository.py` | Built |
| `pipeline.*` task registrations (6) | `api/pipeline/tasks.py` | Built — registered; bodies raise `NotImplementedError` until S2/S3 |
| `pipeline.parse_and_chunk` / `segment_chapters` / `embed_chunks` bodies | `api/pipeline/tasks.py` | Built |
| `render_page`, `PageOutOfRangeError` | `api/pipeline/render.py` | Built — renders straight from the source PDF via `pypdfium2`, not Docling; caches PNG + span JSON at `books/{id}/pages/{n}.{png,json}` |
| `ObjectStore.put_bytes` / `get_bytes` | `api/pipeline/storage.py` | Built — small in-memory payloads (page renders, span metadata), alongside the streaming `put_stream`/`get_object` pair |
| `pass2_candidates` prefilter | `api/pipeline/` | S4 |
| scene segmentation, speaker attribution | `api/pipeline/` | S4 |

## Known defects — do not rediscover these

1. ~~`api/tasks.py` does not parse.~~ **Fixed at the freeze.** It now holds the
   Celery app, the frozen `STAGES` tuple and `ingestion_chain(book_id,
   from_stage=…)`. It is orchestrator-owned: register your tasks under the
   frozen names in your own module, never edit this file.
2. ~~`CACHE_DIR` is an absolute host path in `chunking.py`.~~ **Fixed in S1.2.**
   Docling's artifacts path now comes from `settings.docling_artifacts_dir` /
   `settings.models_cache_dir`. One absolute host path survives, in
   `api/llm.py` — the Sprint 1 LLM prototype, replaced wholesale by `api/llm/`
   in S2.7 (see SCR-2). No new absolute path may be introduced
   ([AGENTS.md](../../../AGENTS.md)).
3. **`_prepare_chapters` breaks after the first item per page**
   (`if count >= 1: break`), so a chapter heading that is not first on its page
   is missed. Fixed in S2.3.
4. **Chapter matching is by heading text equality**, which collides when two
   chapters share a title. Fixed in S2.3.
5. ~~`SentenceTransformer` and the Docling converter are constructed per call.~~
   **Fixed in S1.2** — both are `lru_cache`d at module scope and pre-loaded by
   the `worker_process_init` handler in `api/workers/app.py`.
6. **`chapter` has no `human_verified` column**, so the repository cannot honour
   the never-overwrite rule for chapters that a human corrected (S7
   `confirm_chapter_split`). Raised as SCR-1; not blocking before S7.
7. **The Docling PDF backend has a confirmed cold-start flake**: the identical
   file converted twice in the same process can report a page as failed on the
   first attempt and succeed on the second (~1/8 empirically). `load_document`
   raises `PageParseError` (`TransientError`) rather than returning a document
   with a silently missing page — Celery's `autoretry_for` absorbs it in
   production. Not a bug to fix; a behaviour to retry around.

## Stage chain

Celery chain, wired by **frozen task-name strings** so BE1 and BE2 never edit
each other's modules:

```
pipeline.parse_and_chunk → pipeline.segment_chapters → pipeline.embed_chunks
→ pipeline.extract_characters → pipeline.resolve_aliases
→ relations.extract → relations.aggregate → graph.upsert
```

`api/tasks.py` declares the chain with `celery_app.signature("<name>")`; each
package registers its own tasks under the frozen name. **Task names are frozen;
implementations are not.**

## Gotchas

- **Page provenance comes from Docling item `prov`.** `chunk.meta.doc_items[*].prov[*].page_no`.
  An empty list is a bug to surface, not a `0` to default to.
- **Embeddings must be normalised** (`normalize_embeddings=True`) — the
  cosine-distance queries assume unit vectors.
- **Contextualize before embedding, store clean text.**
  `chunker.contextualize(chunk)` prepends headings for the embedding; the stored
  `text` stays clean for citation display. Do not conflate them.
- **Chapter carry-forward:** chunks inherit the most recent detected chapter, so
  mid-chapter chunks with no heading still know their chapter.
- **Resume mid-book** by processing only rows that still need work
  (`WHERE text_embedding IS NULL`), not by restarting the stage.
- **A malformed PDF is a permanent error.** Retrying it four times wastes twenty
  minutes. Classify errors before setting `autoretry_for`.
- **Two agents cannot both load BGE-M3 on the GPU.** Worktrees set
  `EMBEDDING_DEVICE=cpu`; GPU embedding runs in integration only
  ([BRANCH.md](../../../BRANCH.md) §9).
- Tokenizer for chunk budgeting is BGE-M3's own (`HuggingFaceTokenizer`,
  `max_tokens=1024`), not a characters/4 estimate.
- **OCR is off by default** (`DocumentChunker(ocr=False)`). RapidOCR downloads
  its own weights from `modelscope.cn` outside the HF cache and claims CUDA
  device 0 regardless of `EMBEDDING_DEVICE` — both break a worktree run and the
  offline-test contract. The corpus is digitally-typeset novels; a scanned book
  opts in explicitly.
- **Page render never goes through Docling.** `pypdfium2` opens and renders
  only the requested page directly from the source PDF — re-converting a
  430-page book through Docling to serve one page would blow the <2s cold
  budget (S2.6). `pypdfium2` and `Pillow` are already locked transitive deps
  of `docling`; no new dependency was declared.
- **`pypdfium2`'s text rects are bottom-left origin, PDF points.** The
  `SpanBox` contract is top-left origin (frozen, `contracts/api.py`) — convert
  once in `render._render_sync` (`y = page_height - top`), never push the
  flip onto a caller.

## Related

[data-model.md](data-model.md) · [llm-runtime.md](llm-runtime.md) ·
[.agents/rules/ingestion.md](../../rules/ingestion.md) ·
[plans/sprint-2/](../../../plans/sprint-2/)

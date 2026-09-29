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
| repository (`create_book`, `get_book_by_hash`, `get_book_by_hash_in_project`, `create_project`, `count_books_in_project`, `bulk_insert_chunks`, `upsert_chapters`, `set_book_status`, `get_stage_statuses`) | `api/pipeline/repository.py` | Built |
| `pipeline.*` task registrations (6) | `api/pipeline/tasks.py` | Built — registered; `reconcile_characters` body still raises `NotImplementedError` until S5 |
| `pipeline.parse_and_chunk` / `segment_chapters` / `embed_chunks` bodies | `api/pipeline/tasks.py` | Built |
| `pipeline.extract_characters` / `resolve_aliases` bodies | `api/pipeline/tasks.py` (logic in `api/extraction/`) | Built (S3) |
| `render_page`, `PageOutOfRangeError` | `api/pipeline/render.py` | Built — renders straight from the source PDF via `pypdfium2`, not Docling; caches PNG + span JSON at `books/{id}/pages/{n}.{png,json}` |
| `ObjectStore.put_bytes` / `get_bytes` | `api/pipeline/storage.py` | Built — small in-memory payloads (page renders, span metadata), alongside the streaming `put_stream`/`get_object` pair |
| `pass2_candidates` prefilter | `api/pipeline/prefilter.py` | Built (S4.10) — chunk-level: keeps a chunk with 2+ distinct roster mentions, or 1 mention when its scene has 2+ participants. `api/relations/scenes.py` (be2, S4.16) reads at scene granularity on top of this; see character-graph.md |
| scene segmentation, speaker attribution | `api/pipeline/scenes.py`, `scene_repository.py`, `speakers.py` | Built (S4.8/S4.9) |
| Session privacy (`get_or_create_upload_session`, `get_visible_project`, `get_visible_book`, `visible_project_ids`, `delete_book_cascade`, `sweep_expired_upload_sessions`) | `api/pipeline/session_privacy.py` | Built (S9.8, ETH-2) — see below |
| Langfuse trace purge on delete | `api/pipeline/tracing_cleanup.py` | Built (S9.8) — best-effort, own lazy client (neither backend agent owns `api/llm/**`) |
| `pipeline.sweep_expired_upload_sessions` task, `beat_schedule` entry | `api/pipeline/tasks.py` | Built (S9.8) — **no beat worker exists in `docker-compose.yml` yet**; the schedule entry is a no-op until do1 adds one (see HANDOFF.md) |

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
6. ~~`chapter` has no `human_verified` column~~ **Fixed in S2's SCR-1
   (migration 0007).** `pipeline/repository.py::upsert_chapters` never writes
   over a verified chapter's number, and since S7.5/S7.6 a re-detection that
   structurally disagrees with one (title/heading/page range/detection
   method — confidence alone does not count, sampling noise moves it every
   run) raises a deduplicated `confirm_chapter_split` review task instead of
   dropping the disagreement silently. `api/review/resolution.py` (be2, S7.2)
   sets `human_verified` when that task resolves.
7. **The Docling PDF backend has a confirmed cold-start flake**: the identical
   file converted twice in the same process can report a page as failed on the
   first attempt and succeed on the second (~1/8 empirically). `load_document`
   raises `PageParseError` (`TransientError`) rather than returning a document
   with a silently missing page — Celery's `autoretry_for` absorbs it in
   production. Not a bug to fix; a behaviour to retry around.

## Upload privacy (Built, S9.8, ETH-2)

`POST /projects` links the new project 1:1 to the caller's `UploadSession`
(migration 0012, `project_id` single-valued — one demo session, one project).
No live `UploadSession` on a project means public (the seeded corpus,
inserted directly by `scripts/seed_series.py`, never through this API).

- **Wrong/missing `X-Session-Token` on a session-owned project is 404, never
  403** — indistinguishable from nonexistent (`session_privacy.get_visible_project`/`get_visible_book`, wired into every route in `routes/books.py`).
  `GET /projects`/`GET /books` filter the same way (`visible_project_ids`).
- **`content_hash` is unique install-wide, but reuse is project-scoped**
  (`get_book_by_hash_in_project`) — a hash collision against a *different*
  project's book is a `409`, never a silent cross-project reuse.
- **Deletion is a raw `DELETE`, not `session.delete(book)`** — the ORM would
  otherwise null every child FK first (`chapter.book_id` is `NOT NULL`,
  relationships carry no `passive_deletes`); Postgres's own `ON DELETE
  CASCADE` (data-model.md) does the real work. Emptying a project deletes the
  project and its `UploadSession` too, plus a Neo4j `reset_project`.
- **be1's own tests never call the graph cascade against live Neo4j**
  (BRANCH.md §4/§9 — be2 has exclusive write access this sprint):
  `test_session_privacy.py` monkeypatches `graph_cascade.remove_book`/
  `graph_projection.reset_project` and asserts they're *called* correctly;
  both are also wrapped in a 20s `anyio.fail_after` so a Neo4j outage never
  blocks deleting what Postgres/MinIO hold. Live-Neo4j verification is
  integration-time (HANDOFF.md).
- **The 24h TTL sweep** (`pipeline.sweep_expired_upload_sessions`) is a real
  Celery task with a `beat_schedule` entry, but **no `celery beat` service
  exists in `docker-compose.yml` yet** (do1-owned) — inert until one is added.

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

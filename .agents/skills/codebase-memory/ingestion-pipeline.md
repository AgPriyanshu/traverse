# Ingestion pipeline

PDF → chunks with page provenance. Symbols over line numbers — `Grep` before
editing.

## Key symbols

| Symbol | Location | Status |
| --- | --- | --- |
| `DocumentChunker.load_document` | `api/document_pipeline/chunking.py` | Built → moves to `api/pipeline/chunking.py` (S1) |
| `DocumentChunker.generate_chunks` | same | Built |
| `DocumentChunker._prepare_chapters` | same | Built — **has bugs, see below** |
| `DocumentChunker._parse_chapter_heading` | same | Built |
| `DocumentChunker._llm_classify_chapter_heading` | same | Built — one call per heading, batch it (S2) |
| `CHAPTER_RE`, `ChapterInfo`, `Chunk` | `api/document_pipeline/constants.py` | Built |
| `_roman_to_int`, `_normalize_chapter_number` | `api/pipeline/chunking.py` | Built |
| `celery_app`, `STAGES`, `ingestion_chain()` | `api/tasks.py` | **Built — frozen, orchestrator-owned** |
| `stage()` status recorder | `api/workers/` | S1 |
| repository (`create_book`, `bulk_insert_chunks`, `upsert_chapters`) | `api/pipeline/repository.py` | S1 |
| `pipeline.parse_and_chunk` / `segment_chapters` / `embed_chunks` | `api/pipeline/tasks.py` | S2 |
| page render service | `api/pipeline/render.py` | S2 |
| `pass2_candidates` prefilter | `api/pipeline/` | S4 |
| scene segmentation, speaker attribution | `api/pipeline/` | S4 |

## Known defects — do not rediscover these

1. ~~`api/tasks.py` does not parse.~~ **Fixed at the freeze.** It now holds the
   Celery app, the frozen `STAGES` tuple and `ingestion_chain(book_id,
   from_stage=…)`. It is orchestrator-owned: register your tasks under the
   frozen names in your own module, never edit this file.
2. **`CACHE_DIR` is an absolute host path** (`/home/prinzz/...`) in
   `chunking.py`. Breaks in every container. Fixed in S1.2; no new absolute path
   may be introduced ([AGENTS.md](../../../AGENTS.md)).
3. **`_prepare_chapters` breaks after the first item per page**
   (`if count >= 1: break`), so a chapter heading that is not first on its page
   is missed. Fixed in S2.3.
4. **Chapter matching is by heading text equality**, which collides when two
   chapters share a title. Fixed in S2.3.
5. `SentenceTransformer` and the Docling converter are constructed **per call**
   in `generate_chunks`. Move to worker scope (S1.2) or every task pays the load.

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

## Related

[data-model.md](data-model.md) · [llm-runtime.md](llm-runtime.md) ·
[.agents/rules/ingestion.md](../../rules/ingestion.md) ·
[plans/sprint-2/](../../../plans/sprint-2/)

# Sprint 2 — Schema & Contract Change Requests

Carried in from Sprint 1. Non-blocking requests batch into the Day-1 freeze.

### SCR-1 · be2 · carried from Sprint 1 · ACCEPTED for the Sprint 2 freeze

**Need:** `GraphEdgeOut.page_refs` is `list[int]` and carries no book dimension.

**Why:** relations are project-scoped, so an edge's evidence can come from more
than one volume. `page_refs: [47, 214]` cannot say which book either page is in
— and in a series a citation without its book is not a citation. This is the
only citation surface in the contracts with that hole. The Neo4j projection
already stores `"<book_order>:<page>"`, so the read path currently discards the
book on the way out.

**Blocking:** no. Bites at Sprint 5 (series) at the latest, and the frozen
contract is what fe1 generates its client from, so it moves at a freeze rather
than mid-sprint.

**Proposed:** a `PageRefOut {book_id, series_order, page}` struct, used by
`GraphEdgeOut.page_refs` and anywhere else a bare page number is returned.
Orchestrator lands it in migration/contract freeze for Sprint 2.

### SCR-2 · do1 · 2026-09-19 · retroactively filed

**Need:** `boto3` (S2.15, `api/ops/storage.py`'s MinIO client) is not in
`api/pyproject.toml`.

**Why:** `api/pyproject.toml` became orchestrator-owned at the Sprint 2 freeze
(BRANCH.md, "`api/pyproject.toml` joined this list at the Sprint 2 freeze").
`api/ops/storage.py` needs an S3 client to talk to MinIO and none of the
dependencies already in the project provide one.

**Blocking:** no. Worked around as a stopgap in `api/Dockerfile`'s runtime
stage (`uv pip install boto3` alongside the existing pytest/ruff stopgap) and
in `.github/workflows/ci.yml`'s `test-api` job, so nothing is blocked pending
the freeze — this entry exists so the dependency lands in `uv.lock` properly
next freeze instead of staying a Dockerfile layer forever.

**Proposed:** add `boto3` to `api/pyproject.toml`'s main dependency group at
the Sprint 3 freeze; delete the `uv pip install boto3` stopgap from
`api/Dockerfile` and `ci.yml` in the same commit.

**Retro note:** this SCR should have been filed in the same commit as
`api/ops/storage.py` (S2.15) — its commit message claimed "SCR filed" but
nothing was appended here. Caught and filed late by the next `do1` session;
flagged for the Sprint 2 retro (BRANCH.md: "a memory/process file that drifts
is worse than none, because agents trust it").

### SCR-5 · be2 · 2026-09-18

**Need:** `settings.reranker_enabled: bool = False` (and, if the reranker
model should also be configurable, `settings.reranker_model_id: str =
"BAAI/bge-reranker-v2-m3"`) in `api/config/settings.py`.

**Why:** S2.10 requires the cross-encoder reranker to sit behind a flag,
default off. `api/config/settings.py` joined the orchestrator-owned list at
the Sprint 2 freeze (BRANCH.md §2, alongside `api/pyproject.toml`), so I
cannot add the field myself.

**Blocking:** no for be1's Day-4 `plan_batches` dependency. Blocking for
S2.10's own acceptance criterion ("`RERANKER_ENABLED` default off") if it
needs to be a real settings-driven flag rather than a provisional
`getattr(settings, "reranker_enabled", False)` in `api/retrieval/rerank.py`
— which is what I've shipped in the meantime so S2.10 isn't fully blocked on
this landing.

**Proposed:** add both fields to `Settings` with the defaults above. No
migration needed — these are process config, not schema.

### SCR-4 · be1 · 2026-09-19

**Need:** `ChunkPayload` (`api/contracts/pipeline.py`) carries no per-chunk
heading list.

**Why:** `pipeline.parse_and_chunk` calls `generate_chunks(document,
embed=False)` deliberately (S2.4 splits embedding into its own stage so an
embedding failure does not force a re-parse). By the time `pipeline.embed_chunks`
runs, the only per-chunk text available is the persisted `documentchunk.text`
column — the *clean* text, per `chunking.py`'s own documented invariant
("contextualize before embedding, store clean text"). `chunker.contextualize`
needs the chunk's headings, which live only on the transient Docling
`DocChunk` object generated during parsing and are never captured in
`ChunkPayload`. `documentchunk.headings` (the DB column) exists but
`bulk_insert_chunks` has always written `[]` to it — there is nothing to put
there without this field.

Net effect: `embed_chunks` currently embeds each chunk's bare `text`, without
the heading context `contextualize()` would have prepended. Not a crash, not
a missing citation — a retrieval-quality gap (heading-less passages are
harder to place semantically) that will show up as recall loss once Sprint 4
starts measuring pass-1/pass-2 candidate quality, not before.

**Blocking:** no. `embed_chunks` ships this sprint with the gap documented
in code (`pipeline/tasks.py::_embed_chunks`) and here; worth closing before
Sprint 4 leans on embedding quality for character-mention retrieval.

**Proposed:** add `headings: list[str] = []` to `ChunkPayload`, threaded
through from `DocChunk.meta.headings` in `generate_chunks`, persisted into
the existing `documentchunk.headings` column by `bulk_insert_chunks`.
`embed_chunks` then embeds `"\n".join(chunk.headings + [chunk.text])` (or
whatever join `contextualize` itself uses — worth checking be2/orchestrator
has no stronger opinion) instead of bare `text`. No migration needed; the
column already exists, unused.

### SCR-6 · fe1 · 2026-09-19

**Need:** `GET /api/books/{book_id}/chunks` takes only `limit`/`offset` — no
`chapter_id` filter.

**Why:** S2.13's chunk inspector opens per chapter and needs that chapter's
chunks. Without a filter it has to page through the whole book (500 at a
time, the server's own cap) and filter client-side by `chunk.chapter_id`,
stopping once it has at least `chapter.chunk_count` matches. Works, but a
1,000-chunk book with a chapter near the end pages needlessly, and it is
strictly worse than a query the server could answer directly.

**Blocking:** no — the client-side workaround (`web/src/routes/book/
chunk-inspector.tsx`) ships in the meantime and is the only chunk-listing UI
in Sprint 2.

**Proposed:** add an optional `chapter_id` query param to
`list_chunks_api_books__book_id__chunks_get`, filtered server-side. Batched
into the next freeze.

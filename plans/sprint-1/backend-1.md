# Sprint 1 · Backend Engineer 1

**Branch:** `ai/be1/sprint-1-foundations` · **Worktree:** `../traverse-wt/be1`
**Read first:** [BRANCH.md](../../BRANCH.md), [sprint-1/README.md](README.md)

## Mission

Make the ingestion machinery *runnable*. The existing `DocumentChunker` works
but only from a notebook on one machine — it hardcodes an absolute cache path,
pins CUDA, loads the embedding model per call, and has no Celery wiring. Turn it
into a worker-safe, config-driven, testable component, and build the repository
layer everything downstream will persist through. No new extraction behaviour
this sprint.

## Owned paths

```
api/pipeline/**  api/workers/**  api/routes/books.py
api/tests/pipeline/**  api/tests/workers/**
```

Forbidden: `api/db/models/**`, `api/db/migrations/**`, `api/contracts/**`,
`api/graph/**`, `api/query/**`, `web/**`, `docker-compose.yml`, `api/tasks.py`.

## Setup

```bash
cd ../traverse-wt/be1/api && uv sync
cat > .env <<'EOF'
POSTGRES_DB_STRING=postgresql+psycopg://postgres:postgres@localhost:5433/traverse_be1
RABBITMQ_URL=pyamqp://guest:guest@localhost:5672/be1
EMBEDDING_DEVICE=cpu
API_PORT=8001
EOF
uv run alembic upgrade head
```

`EMBEDDING_DEVICE=cpu` is not optional — two agents loading BGE-M3 onto one
consumer GPU will OOM (BRANCH.md §9).

---

## S1.1 — Celery worker bootstrap

Move the existing `celery_app` out of `api/tasks.py` (orchestrator-owned) into
`api/workers/app.py` and import it back. Configure:

- Broker from `settings.rabbitmq_url`, result backend `rpc://`
- `task_acks_late=True`, `worker_prefetch_multiplier=1` — ingestion tasks are
  long and must not be lost on worker death
- `task_track_started=True`
- Per-task `autoretry_for=(TransientError,)`, `retry_backoff=True`,
  `retry_backoff_max=300`, `max_retries=4` (F1.2 exponential backoff)
- `worker_process_init` signal warms Docling models and the embedding model
  **once per process** — the TODO's "warmup code for Sentence Transformer"

Register tasks under the frozen names from the registry. Implementations may be
`NotImplementedError` this sprint; **the names must appear in
`celery inspect registered`**, because DO1's healthcheck asserts on them.

**S1.1 — stage status recorder.** A context manager writing `IngestionStage`
rows so `GET /books/{id}/status` has something to read:

```python
async with stage(book_id, "pipeline.embed_chunks") as s:
    ...                      # sets running → succeeded, or failed with the traceback
```

*Acceptance:* `celery -A api.workers.app inspect registered` lists all 8 frozen
names. Killing a worker mid-task leaves the stage row `running`, and the retry
transitions it correctly rather than orphaning it.

## S1.2 — Config-driven chunker

Refactor `api/document_pipeline/chunking.py` → `api/pipeline/chunking.py`:

- `CACHE_DIR` and `EMBEDDING_MODEL_ID` come from settings, never module
  constants. **This is the Sprint 1 blocker** — the current absolute path fails
  in every container.
- `SentenceTransformer` and the Docling converter load once at module/worker
  scope, not per `generate_chunks` call.
- `device` from `settings.embedding_device`, with a CPU fallback that warns
  rather than crashing.
- `DocumentChunker.__init__(self, settings=...)` — injectable for tests.
- Keep the chapter carry-forward and page-provenance logic exactly as-is. It
  works; do not redesign it this sprint.
- Return `list[ChunkPayload]` from `api/contracts/pipeline.py` instead of the
  local `Chunk` dataclass.

*Acceptance:* `pytest api/tests/pipeline/test_chunking.py` passes on CPU with no
GPU present and no network access, using a 3-page fixture PDF. No absolute path
appears in `grep -rn "/home/" api/`.

## S1.3 — Repository layer

`api/pipeline/repository.py` — the only place ingestion touches the DB:

```python
async def create_book(session, *, title, author, content_hash, page_count) -> Book
async def get_book_by_hash(session, content_hash) -> Book | None     # F1.5
async def bulk_insert_chunks(session, book_id, payloads: list[ChunkPayload]) -> int
async def upsert_chapters(session, book_id, chapters: list[ChapterInfo]) -> list[Chapter]
async def set_book_status(session, book_id, status: BookStatus) -> None
async def get_stage_statuses(session, book_id) -> list[StageStatus]
```

Bulk insert uses a single `insert().values(...)` with `execution_options` —
inserting 800 chunks row-by-row is a 30-second stall. Chunks carry `chapter_id`
resolved from chapter number, not a dangling string.

*Acceptance:* Integration test inserts 500 synthetic chunks in under 2 seconds
and round-trips `pages[]`, `page_start`, `page_end` intact. Re-creating a book
with an existing `content_hash` returns the existing row and inserts nothing.

## S1.4 — `GET /books` and `GET /books/{id}/status`

Implement two of the `books.py` stubs against the repository. Upload stays a 501
stub — real upload is Sprint 2, and shipping half of it now means FE1 codes
against a shape that changes.

---

## Definition of Done

- [ ] All frozen task names registered and visible to `celery inspect`
- [ ] Chunker runs CPU-only in a container with no host paths
- [ ] Repository has tests against a real Postgres (`traverse_be1`), not mocks
- [ ] `ruff check` clean
- [ ] `HANDOFF.md`: repository function signatures BE2 will call in Sprint 4

## Escalate immediately if

- A contract in `api/contracts/pipeline.py` does not fit what Docling actually
  returns → SCR, do not work around it locally
- The `0006` migration disagrees with what the repository needs → SCR
- Docling model download is required at test time → tell DO1; tests must not
  hit the network

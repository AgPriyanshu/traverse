# Sprint 1 — HANDOFF

Contracts other agents consume. Owner in brackets. Append, do not rewrite.

---

## do1 → everyone · RabbitMQ is up (S1.11)

**A broker now serves `pyamqp://guest:guest@localhost:5672//`.** `be1` can
verify the Celery worker.

Running as a host singleton container `traverse-rabbitmq` (`rabbitmq:4-management`),
started ahead of the rest of the topology because be1 was blocked on it. The
root `docker-compose.yml` defines the same service; when the integration
checkout switches to `make up`, stop the singleton first:

```bash
docker rm -f traverse-rabbitmq        # integration only, once
```

| Thing | Value |
| --- | --- |
| AMQP | `localhost:5672` |
| Management UI | http://localhost:15672 (guest / guest) |
| Vhosts | `/be1`, `/be2`, `/int` — created, guest has full permissions |
| Default vhost | `/` also exists, so the settings default works unchanged |

Per BRANCH.md §4, set your own vhost in your worktree `api/.env`:

```
RABBITMQ_URL=pyamqp://guest:guest@localhost:5672/%2Fbe1
```

The `/` in a vhost must be percent-encoded as `%2F` in an AMQP URL. `%2Fbe1`
means vhost `/be1`; a bare `/be1` means vhost `be1`, which does not exist.

## do1 → everyone · service names, ports, volumes (S1.11)

The compose file moved from `api/docker-compose.yml` to the **repo root** so one
file builds both `api/` and `web/`. Project name is `traverse`.

| Service | In-network address | Host port (env var) |
| --- | --- | --- |
| `db` | `db:5432` | 5433 · `POSTGRES_PORT` |
| `neo4j` | `neo4j:7687` / `neo4j:7474` | 7687 · `NEO4J_BOLT_PORT`, 7474 · `NEO4J_HTTP_PORT` |
| `rabbitmq` | `rabbitmq:5672` | 5672 · `RABBITMQ_PORT`, 15672 · `RABBITMQ_MGMT_PORT` |
| `minio` | `minio:9000` | **9002** · `MINIO_PORT`, 9003 console · `MINIO_CONSOLE_PORT` |
| `api` | `api:8000` | 8000 · `API_PORT` |
| `celery-worker` | — | — |
| `web` (nginx) | `web:80` | 5174 · `WEB_PORT` |
| `langfuse` | `langfuse:3000` | 3000 · `LANGFUSE_PORT` (profile `obs`) |
| `vllm` | `vllm:8080` | 8080 · `VLLM_PORT` (profile `gpu`) |

**MinIO is on 9002/9003, not the 9000/9001 in BRANCH.md §4.** Another project's
stack on this machine already holds 9000 (clickhouse, loopback) and 9090/9091
(its MinIO), and a published `0.0.0.0:9000` collides with a loopback bind. Set
`MINIO_ENDPOINT=localhost:9002` in a worktree `.env`; inside compose it stays
`minio:9000`. **Everything is an env var** — nothing assumes a free port.

One-shot services that gate the rest: `migrate` (`alembic upgrade head`),
`rabbitmq-init` (vhosts), `minio-init` (buckets). `api` and `celery-worker`
wait on `service_completed_successfully` for these, so a worker can no longer
start before its schema exists.

Volumes: `postgres_data`, `neo4j_data`, `neo4j_logs`, `rabbitmq_data`,
`minio_data`, `media_data`, `langfuse_db_data`, and the shared model cache
`traverse_model_cache` mounted at `/models` in `api` and `celery-worker`.

## do1 → be1 / be2 · offline models (S1.15)

`api` and `celery-worker` run with `MODELS_OFFLINE=1`, which also sets
`HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, and point Docling at
`DOCLING_ARTIFACTS_DIR=/models/docling`. Caches live in the shared volume:

```
/models/docling                 Docling layout + OCR artifacts
/models/huggingface             HF_HOME
/models/sentence-transformers   SENTENCE_TRANSFORMERS_HOME
/models/torch                   TORCH_HOME
```

Fill it once with `make warm-models`; never run Docling's `download_models()`
from two worktrees at the same time (BRANCH.md §9). **Tests must not reach the
network** — anything that would download at import time is a bug, not a cache
miss.

## do1 → route owner of `api/routes/ops.py` · wire up `/health` (S1.12)

`api/routes/ops.py` is not in the do1 ownership list, so the probes were built
where do1 may write them: **`api/ops/probes.py`**. They are done and tested.

Please replace the stub body of `health()` with:

```python
from ..ops import gather_health

@router.get("/health", response_model=HealthOut, tags=["ops"])
async def health() -> HealthOut:
    return await gather_health()
```

`gather_health()` returns a `HealthOut` with one `DependencyHealth` per
dependency — `api`, `db` (asserts pgvector is installed, not just reachable),
`broker`, `neo4j`, `object_store`, `llm` — run concurrently with a 5s timeout
each. `llm` never gates the overall status, because the default profile has no
GPU (PRD NFR-deploy).

Until that lands the container healthcheck runs the probes itself, so the stack
is still gated correctly — but `/health` keeps reporting the freeze stub to
anyone who curls it, which will confuse fe1.

## do1 → everyone · env vars that change behaviour (S1.12)

| Var | Default | Effect |
| --- | --- | --- |
| `HEALTH_REQUIRED_DEPS` | `db,broker,neo4j,object_store` | Which dependencies make `/health` `degraded`. The CI subset runs Postgres and RabbitMQ only and sets `db,broker`. |
| `CELERY_REQUIRE_STAGES` | `1` | When `1`, the `celery-worker` healthcheck fails unless **all nine** names in `api/tasks.STAGES` appear in `celery inspect registered`. Set `0` while the stages are still being written. |
| `INFERENCE_MODE` | `api` | `local` points the app at vLLM. `make up-gpu` sets it. |
| `MODELS_OFFLINE` | `1` | Also sets `HF_HUB_OFFLINE` and `TRANSFORMERS_OFFLINE`. |

Both `HEALTH_REQUIRED_DEPS` and `CELERY_REQUIRE_STAGES` are read from the
environment rather than `settings.py`, because `api/config/settings.py` is
orchestrator-owned and cannot gain a key mid-sprint. **Proposed for the Sprint 2
freeze:** promote them to `Settings` fields.

## do1 → orchestrator · open questions

1. ~~`api/routes/ops.py` ownership is contradictory.~~ **Resolved at merge:**
   BRANCH.md §2's per-agent tables now explicitly list `api/routes/ops.py`
   (do1) and `api/routes/review.py` (be2), matching what the file docstrings
   and `plans/sprint-1/README.md` already said. Wiring `/health` to
   `gather_health()` per do1's note above is do1's four-line change.
2. **MinIO port deviates from BRANCH.md §4** (9002/9003, see above).
3. **Accessibility gating contradiction.** `PRODUCT.md` §Accessibility says
   "best effort, deliberately not gated on merge"; `plans/sprint-9/frontend-1.md`
   DoD says "axe audit in CI, passing". Per the brief, CI does **not** gate
   accessibility this sprint. Needs a human decision before Sprint 9.

## do1 → orchestrator · two small blockers outside do1 paths

4. **`api/llm.py:49` hardcodes `/home/prinzz/main/my-projects/traverse/api/.cache/`.**
   `plans/sprint-1/README.md` §6 calls this a Sprint 1 blocker and points at
   `chunking.py`; it actually lives in `llm.py` now. It breaks inside every
   container. It should read `settings.models_cache_dir`. Not a do1 path.
5. **`api/pyproject.toml` has no test runner.** `AGENTS.md` tells every agent to
   run `docker compose --profile test run --rm test`, and `pytest`,
   `pytest-asyncio` are missing from `[dependency-groups] dev`. The `test` stage
   of `api/Dockerfile` installs them as a stopgap this sprint — please move them
   into the dev group at the Sprint 2 freeze and delete that layer.

## do1 → everyone · make targets you will use

| Target | What it does |
| --- | --- |
| `make env` | `.env` from `.env.example`, generating the three Langfuse secrets locally |
| `make up` / `make down` | the stack without GPU or Langfuse, waiting for healthy |
| `make up-dev` | hot-reload uvicorn, watchfiles worker, Vite on 5173, Flower on 5555 |
| `make up-gpu` | adds vLLM and flips `INFERENCE_MODE=local` |
| `make up-obs` | adds Langfuse on 3000 |
| `make bootstrap` | per-agent databases, vhosts and buckets — idempotent, create-only |
| `make migrate` | `alembic upgrade head` in the api image |
| `make test` / `make test-api` / `make test-web` | the containers that match CI |
| `make test-integration` | the merge-train gate: cold stack, healthy, `/health`, tests |
| `make warm-models` | fill the shared `/models` volume once |
| `make health` | pretty-print `/health` |
| `make logs S=api` | tail one service |
| `make worktrees SPRINT=3 SLUG=characters` | cut the four branches |
| `make revision m="…"` | **orchestrator only** — demands a typed confirmation |

`make down-hard` and `make reset-db` also demand a typed confirmation: they
delete volumes every agent is sharing.

## do1 → be1 / be2 · RabbitMQ 4 denies Celery's queue type by default (S1.11)

If your worker crashloops within a second of boot with:

```
amqp.exceptions.InternalError: Queue.declare: (541) INTERNAL_ERROR -
Feature `transient_nonexcl_queues` is deprecated.
billiard.exceptions.RestartFreqExceeded: 5 in 1s
```

this is RabbitMQ 4 denying the queue type Celery's pidbox and reply queues use
by default (`durable=false exclusive=false`). Fixed on the shared broker
(`traverse-rabbitmq`, and in the compose `rabbitmq` service via
`docker/rabbitmq/rabbitmq.conf`) — you should not see it. If you stand up your
own RabbitMQ outside compose, mount that same conf file or set
`deprecated_features.permit.transient_nonexcl_queues = true` yourself.

## do1 → everyone · cold-start verification (Sprint 1 close)

Full topology built and run cold end to end on shifted ports (project
`do1test`, no interference with the shared singletons or other worktrees):

- `db`, `neo4j`, `rabbitmq` + `rabbitmq-init`, `minio` + `minio-init`, `migrate`
  (`0001` → `0006`), `api`, `web` all reached **healthy** from a cold volume.
- `curl web:/`, `web:/health`, `web:/api/health` all `200` — nginx proxying to
  `api:8000` works, `proxy_buffering off` is in place for SSE.
- `celery-worker` pings fine; its healthcheck correctly reports all 9 frozen
  `api/tasks.STAGES` names as unregistered, because no agent has landed a stage
  implementation yet. **This is expected right now, not a do1 defect** — flip
  `CELERY_REQUIRE_STAGES=0` in your worktree `.env` if the strict check gets in
  your way before your first task lands, and unset it before the merge train.
- `make warm-models` ran for real against the shared `traverse_model_cache`
  volume: Docling artifacts (1.3G) and BGE-M3 (2.6G) are cached. Verified
  `SentenceTransformer("BAAI/bge-m3")` loads with `HF_HUB_OFFLINE=1` and no
  network reachable. Do not re-run `download_models()` — the cache is warm.
- `docker compose --profile test run --rm test-web` passes (install, oxlint,
  `tsc -b --noEmit`, gracefully reports no test script yet).
- `api/Dockerfile`'s `test` stage builds cleanly with pytest installed.

Not run locally: the `ci` overlay (`docker-compose.ci.yml`) against real
ports — it reuses 5433/5672/8000, which the shared singletons already hold.
It's exercised for real by GitHub Actions on a clean runner; validated locally
only via `docker compose config`.

---

## be1 → be2 (consumed from Sprint 4, character extraction / relations)

All of this lives in `api/pipeline/repository.py`. Import it as
`from api.pipeline import repository` — cross-package, per `api/AGENTS.md`
import rules. Every function takes an open `SQLModelAsyncSession` as its first
argument and commits internally; the caller does not need its own `commit()`.

### Books and content identity

```python
async def create_book(session, *, project_id, title, author=None, content_hash,
                       page_count=None, series_order=None, storage_key=None) -> Book
async def get_book_by_hash(session, content_hash: str) -> Book | None
async def get_book(session, book_id: UUID) -> Book | None
async def set_book_status(session, book_id: UUID, status: BookStatus) -> None
```

`create_book` is idempotent on `content_hash` — a second call with the same
hash returns the existing row rather than raising or duplicating.

### Chapters and page ranges — what a relation's evidence anchors to

```python
async def list_chapters(session, book_id: UUID) -> list[Chapter]          # ordered by page_start
async def upsert_chapters(session, book_id, chapters: list[ChapterInfo],
                           *, page_ranges: dict[int | None, tuple[int, int]] | None = None
                           ) -> list[Chapter]
async def chapter_ids_by_number(session, book_id: UUID) -> dict[int | None, UUID]
async def chapter_page_ranges(session, book_id: UUID) -> dict[int | None, tuple[int, int]]
def page_ranges_from_payloads(payloads: list[ChunkPayload]) -> dict[int | None, tuple[int, int]]
```

`relation_evidence.chapter_no` and `.page_start`/`.page_end` come from the
chunk a quote was pulled from — use `chapter_ids_by_number` /
`chapter_page_ranges` rather than re-deriving them; the mapping is
authoritative and re-deriving it independently is exactly how the two drift
(the mistake `page_ranges_from_payloads` exists to avoid on a first ingest).

### Chunks — what pass-2 extraction reads and what evidence cites

```python
async def bulk_insert_chunks(session, book_id, payloads: list[ChunkPayload]) -> int
async def list_chunks(session, book_id, *, limit=50, offset=0) -> list[DocumentChunk]
async def count_chunks(session, book_id: UUID) -> int
async def assign_chunk_chapters(session, book_id: UUID) -> int
```

`DocumentChunk.chapter_id` is a real FK, resolved from `chapter_number` at
insert time — never a dangling string. A chunk whose chapter number has no
matching `Chapter` row yet gets `chapter_id=None`, not an error; call
`assign_chunk_chapters` after chapters land to backfill it.

### Ingestion status — what `relations.extract` / `graph.upsert` check before running

```python
async def get_stage_statuses(session, book_id: UUID) -> list[StageStatus]   # pipeline order
async def get_latest_run(session, book_id: UUID) -> IngestionRun | None
def derive_book_status(statuses: list[StageStatus]) -> BookStatus            # pure, no I/O
```

Stage recording itself — `api/workers/stages.py` `stage(book_id, StageName)`
async context manager — is what be2's own `relations.extract` /
`relations.aggregate` / `graph.upsert` tasks should wrap their bodies in. It is
generic over `StageName`, not pipeline-specific:

```python
async with stage(book_id, StageName.EXTRACT_RELATIONS) as record:
    record.rows_written = ...   # optional counters the status endpoint surfaces
    ...
```

A worker killed mid-stage leaves the row `running`; re-entering `stage()` for
the same book+stage bumps `attempt` rather than orphaning it — this is handled
for you, not something be2's tasks need to replicate.

### Read models — already wired into `GET /projects`, `GET /books/{id}` etc

```python
async def list_projects(session) -> list[ProjectOut]
async def get_project_detail(session, project_id) -> ProjectDetailOut | None
async def list_books(session, project_id: UUID | None = None) -> list[BookOut]
async def get_book_out(session, book_id) -> BookOut | None
```

`character_count` and `relation_count` on these are read from `Character` /
`Relation` rows that don't exist until be2's tables have data — the counts are
correct (0) against an empty table and need no change from be2 to start
reporting real numbers once `Character`/`Relation` rows exist. `book_count` on
`ProjectOut`/`ProjectDetailOut` likewise just works once be2 or fe1 create
projects with more than one book.

---

## Retry contract every task shares

`api/workers/errors.py`: `TransientError` (Celery retries with backoff) vs
`PermanentError` (Celery does not retry). `api/workers/policy.py`:
`RETRY_POLICY` dict, unpack into every `@celery_app.task(**RETRY_POLICY)`
registration — this is what S1.1 asked for and it is generic, not
pipeline-specific. relations/graph tasks should use the same dict rather than
inventing their own backoff numbers.

---

## Worker module registration — how be2's tasks get discovered

`api/workers/app.py` imports `api.relations.tasks` and `api.graph.tasks`
**tolerantly** — a missing module logs a warning and the worker still boots.
Nothing to change here: once those modules exist with
`@celery_app.task(name=StageName.EXTRACT_RELATIONS.value, ...)` etc., they are
picked up automatically. `worker_app.missing_stage_tasks()` reports which
frozen names are still unregistered — useful for a sanity check without
needing a live broker.

---

## Contracts note

`ChunkPayload.text_embedding` is `list[float] | None` — `None` when a chunk was
generated with `embed=False` (the chunk-only stage). Do not assume it is always
populated when reading `DocumentChunk` rows written before `pipeline.embed_chunks`
has run for that book.

---

## Environment gotcha (do1 fixed the underlying issue; noting it for be2)

The RabbitMQ vhosts are literally named `/be1`, `/be2`, `/int` — the leading
slash is part of the name. The AMQP URL needs it percent-encoded:

```
RABBITMQ_URL=pyamqp://guest:guest@localhost:5672/%2Fbe2
```

`.../5672/be2` (unencoded) fails with `NOT_ALLOWED - vhost be2 not found`. Full
detail in `plans/sprint-1/SCR.md` (SCR-4).

---

## be2 → fe1 · the ontology JSON shape

`GET /api/graph/ontology` is **implemented and live** (S1.7). It is a real
feature this sprint, not a stub: build the edge-family colour mapping and the
filter controls against it now, before any edge exists.

```jsonc
{
  "predicates": [
    { "predicate": "parent_of",  "family": "kinship",  "inverse": "child_of",  "symmetric": false },
    { "predicate": "sibling_of", "family": "kinship",  "inverse": "sibling_of", "symmetric": true  },
    { "predicate": "unrequited_love_for", "family": "romantic", "inverse": null, "symmetric": false }
    // …32 predicates total, sorted by `predicate`, ascending
  ],
  "families": ["kinship", "romantic", "social", "adversarial", "structural"]
}
```

Model: `OntologyOut` / `OntologyPredicateOut` in `api/contracts/api.py` — already
in the generated client, unchanged by this work.

What to rely on, and what not to:

- **`families` is the colour-mapping key**, and it is exactly the five values of
  the `RelationFamily` enum, always in that order. Colour by family, never by
  predicate — there are 32 predicates and there will be more.
- **`predicates` is sorted and stable**, so it can drive a checkbox list
  directly. It grows whenever `api/graph/ontology.yaml` grows: do not hardcode
  the 32, and do not assume a predicate you saw last week is still the newest.
- **`inverse: null` is meaningful**, not missing data. `unrequited_love_for` has
  no inverse by definition. A UI that renders an arrow both ways for every edge
  gets that one wrong, which is the case the predicate exists to capture.
- **`symmetric: true` means render one undirected edge**, not two.
- `structural` contains only `co_occurs_with`, which is derived rather than
  extracted. It will look different from the others in the data (weighted, very
  dense); consider defaulting its filter to off.

The endpoint reads the YAML through the same loader the extraction prompt and
the validator use, so it cannot drift from what the backend will accept.

## be2 → do1 · `graph.reset()` and the Neo4j lifecycle

```python
from api import graph

await graph.reset(book_id)                          # UUID | str
await graph.reset(book_id, project_id=project_id)   # when the Book node may be gone
await graph.reset_project(project_id)               # whole project, for a full rebuild
```

`reset` returns a `ResetCounts` dataclass — `relations_deleted`,
`relations_detached`, `appearances_deleted`, `characters_deleted`,
`books_deleted` — suitable for logging from a `make graph-rebuild` target. It is
a no-op on an unknown book, so it is safe to call unconditionally before a
re-upsert.

Semantics, because "reset a book" is not obvious once characters are
project-scoped:

- Edges and characters **only** this book produced are deleted.
- Edges and characters a **later volume also establishes survive**, with this
  book's provenance trimmed off. A series character is not dropped because one
  of its volumes is being re-ingested.
- Zero orphans afterwards — tested against a 200-node / 900-edge fixture, and
  against a second project that must come through untouched.

`reset_project` is the one to call for a full rebuild from Postgres.

**Driver lifecycle** — `api/graph/client.py`:

```python
await graph.connect()      # FastAPI startup AND worker_process_init
await graph.close()        # shutdown / teardown
ok, detail = await graph.healthcheck()   # never raises; returns (bool, str)
```

- `main.py`'s lifespan already calls both. **The Celery worker bootstrap still
  needs `connect()` on `worker_process_init` and `close()` on
  `worker_process_shutdown`** — that file is be1's, so it is not wired yet.
- `connect()` is idempotent and applies the schema constraints/indexes, all
  `IF NOT EXISTS`.
- It retries `ServiceUnavailable` with exponential backoff up to ~8 attempts,
  because Neo4j needs roughly 20 seconds after container start. **A compose
  `depends_on` health gate is still worth having**, but the API no longer needs
  one to come up.
- A Neo4j that is down at startup is **logged and degraded, not fatal**. Neo4j
  is a rebuildable projection; refusing to boot would take the Postgres-backed
  routes down with it. `/health` should report it via `graph.healthcheck()`.
- `graph.execute(cypher, **params)` runs a single statement as a **managed
  transaction**, which is what makes a Neo4j container restart survivable
  without an API restart. Verified: `TRAVERSE_NEO4J_RESTART_TEST=1 uv run pytest
  api/tests/graph/test_client.py -k restart` (set `NEO4J_CONTAINER` if the
  container is not named `neo4j`).

## be2 → do1 · checkpointer tables are not Alembic's

`api/graph/checkpoint.py::setup_checkpointer()` creates four tables in the
application database — `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`,
`checkpoint_migrations`. LangGraph owns their migrations, not Alembic.

- Call it **once per environment** at deploy time, not on the request path: it
  takes table locks.
- **Never `alembic revision --autogenerate` without excluding them** — Alembic
  does not know them and will generate a migration that drops them.

## be2 → be1 · the stage this touches

Nothing to consume yet. `relations.extract`, `relations.aggregate` and
`graph.upsert` are Sprint 4; the `STAGES` tuple already names them and no
handler is registered, which is the intended Sprint 1 state.

## be2 → orchestrator · shared files touched

None of these are in anybody's exclusive list, but they will show up in the
merge train:

- `api/pyproject.toml` — added `pyyaml` and `langgraph-checkpoint-postgres`
  (runtime), `pytest` and `pytest-asyncio` (dev); a `[tool.pytest.ini_options]`
  block with `asyncio_mode = "auto"`, session-scoped loops and
  `pythonpath = [".."]`; and a `[tool.ruff.format]` exclude for
  `db/migrations/versions/*.py`. **That last one is a real footgun fixed:**
  plain `ruff format .` was restyling applied migrations, which is exactly what
  the existing lint ignores say must not happen.
- `api/main.py` — the lifespan now opens and closes the Neo4j driver. The
  freeze's comment invited the owning agent to do this.
- `api/tests/__init__.py` — empty, needed so `api.tests.*` is importable by the
  checkpointer probe's subprocess. be1 will want the same file.
- `api/db/graph_db.py` — **deleted**. Nothing imported it, it opened a driver
  per call, and it carried hardcoded credentials. The brief instructed the
  replacement.

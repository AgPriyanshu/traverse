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

1. **`api/routes/ops.py` ownership is contradictory.** BRANCH.md §2 does not
   grant do1 `api/routes/**`; `plans/sprint-1/README.md` §4 and the file's own
   docstring both say `ops.py` is do1's. Resolve it — the probes are written
   either way, but somebody has to land the four-line route change.
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

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

# Infra topology

What runs where, and how four agents share one machine. Symbols over line
numbers.

## Current state

**Built (S1):** `docker-compose.yml` at the **repo root** — it moved out of
`api/` so one file builds both `api/` and `web/`. Project name `traverse`.
Overlays `docker-compose.dev.yml`, `.gpu.yml`, `.ci.yml`. `api/Dockerfile`
(multi-stage uv, non-root, `test` stage), `web/Dockerfile` + `web/nginx.conf`,
`Makefile`, `.env.example`, `scripts/**`, `.github/workflows/ci.yml`,
`api/ops/probes.py`. `api/routes/ops.py` is do1-owned as of the Sprint 2
freeze (BRANCH.md) — `/health` wiring to `api.ops.gather_health` landed in
Sprint 1, not a gap.

**Built (S2):** `api/ops/storage.py` (S2.15 — MinIO `put_stream`/`exists`/
`presigned_get`/`delete_prefix`, a 30-day lifecycle rule on `books/*/pages/*`).
`api/ops/metrics.py` + `api/ops/tracing.py` (S2.17 — cost table and Langfuse
trace/span helpers; wiring the two call sites into `api/workers/stages.py` is
be1's, see `plans/sprint-2/HANDOFF.md`). `api/ops/pipeline_status.py` wired
into real `GET /api/ops/metrics` / `/ops/pipeline/runs` /
`/ops/pipeline/dead-letter` handlers (S2.17/S2.18 — no more 501s). `make seed`
→ `scripts/seed_corpus.py` (S2.16 — the real five-novel PRD §7 corpus, stdlib
PDF writer, `corpus/manifest.json` + `corpus/LICENSES.md` committed,
`corpus/downloads/*` gitignored). `make test-integration` now runs a fixture-
novel ingestion through the real API (`scripts/test_integration_ingestion.py`,
S2.18) in addition to the cold-boot health check; `.github/workflows/
nightly-corpus.yml` + `scripts/nightly_corpus_ingestion.py` post the real
corpus's wall clock/cost nightly. Both ingestion scripts currently skip with
exit 0 on a 501 from `POST /api/projects/{id}/books` — that's S2.1 (be1) not
merged into the checkout being tested yet, not a bug; see HANDOFF.md.

**Broken / partial:** the Sprint 1 `api/llm.py` `CACHE_DIR` absolute-path
defect is gone — fixed by the Sprint 2 contract freeze (`3cdc9fb`), confirmed
by `grep -rn "/home/" .` returning nothing outside `.gitignore`d files.
`make test-integration`'s <8-minute budget is unverified end to end (tearing
down the shared singleton stack to time it would have disrupted every other
worktree mid-sprint — see HANDOFF.md). The nightly corpus job's wall clock is
API-inference, not the local-vLLM number NFR-perf is judged on (no GPU on
`ubuntu-latest`).

**Not built:** anything Sprint 3+.

## Services

| Service | Image / build | In-network | Host port (env var) |
| --- | --- | --- | --- |
| `db` | `pgvector/pgvector:pg18-trixie` | `db:5432` | 5433 · `POSTGRES_PORT` |
| `neo4j` | `neo4j:5-community-trixie` | `neo4j:7687` | 7687 · `NEO4J_BOLT_PORT`, 7474 · `NEO4J_HTTP_PORT` — **single database only** |
| `rabbitmq` | `rabbitmq:4-management` | `rabbitmq:5672` | 5672 · `RABBITMQ_PORT`, 15672 · `RABBITMQ_MGMT_PORT` |
| `minio` | `minio/minio` | `minio:9000` | **9002** · `MINIO_PORT`, 9003 console |
| `api` | `api/Dockerfile` | `api:8000` | 8000 · `API_PORT` |
| `celery-worker` | same image | — | — |
| `web` | `web/Dockerfile` (nginx) | `web:80` | 5174 · `WEB_PORT` |
| `langfuse` + `langfuse-db` | `langfuse/langfuse:2` | `langfuse:3000` | 3000 · `LANGFUSE_PORT` |
| `vllm` | `vllm/vllm-openai` | `vllm:8080` | 8080 · `VLLM_PORT` |

One-shots that gate the rest, via `service_completed_successfully`: `migrate`
(`alembic upgrade head`), `rabbitmq-init` (vhosts), `minio-init` (buckets).

**Every host port is an env var with a default.** Another project's stack
already holds 9000 and 9090/9091 on this machine, which is why MinIO is on
9002/9003 and not the 9000/9001 in BRANCH.md §4.

## Profiles

| Profile | Contents |
| --- | --- |
| *(none)* | db, neo4j, rabbitmq, minio, their init jobs, migrate, api, celery-worker, web |
| `gpu` | adds vLLM. Use `make up-gpu`, which also flips `INFERENCE_MODE=local` |
| `obs` | Langfuse and its own Postgres. Opt-in: it needs generated secrets |
| `test` | `test` (pytest) and `test-web` (oxlint + tsc) |

`ci` is **not** a compose profile — a profile only *adds* services, so
`--profile ci` could never mean "Postgres and RabbitMQ only". It is an explicit
service subset: `make ci-up` plus the `docker-compose.ci.yml` overlay.

Compose cannot vary an env value by profile, so `INFERENCE_MODE` is flipped by
`docker-compose.gpu.yml`, not by the `gpu` profile.

## Agent isolation

Infra containers are **host singletons** started once from the integration
checkout. Isolation is at the database and port level, not the container level.
`scripts/bootstrap_databases.sh` (or `make bootstrap`) creates all three slices
and is idempotent and create-only, so it is safe to run while others are working.

| Resource | Isolation |
| --- | --- |
| Postgres | `traverse_be1`, `traverse_be2`, `traverse_int`, each with `vector` |
| Neo4j | **be2 exclusive** — Community edition is single-database |
| RabbitMQ | vhost per agent: `/be1`, `/be2`, `/int` |
| MinIO | bucket per agent |
| vLLM | **shared** — one GPU. Timings from a worktree are invalid. |
| FastAPI | 8000 int · 8001 be1 · 8002 be2 · 8003 fe1-mock |
| Vite | 5173 fe1 · 5174 int |

## Healthchecks assert behaviour

| Service | Check |
| --- | --- |
| `db` | `pg_isready` **and** `SELECT 1 FROM pg_extension WHERE extname='vector'` |
| `neo4j` | `cypher-shell "RETURN 1"` |
| `rabbitmq` | `rabbitmq-diagnostics check_running` |
| `minio` | `mc ready local` |
| `api` | `python -m api.ops.healthcheck api` — GETs `/health`, then runs the probes |
| `celery-worker` | `celery inspect ping` **plus** all nine `api/tasks.STAGES` names in `inspect registered` |
| `vllm` | `GET /v1/models` |

Two env vars change what "healthy" means, and both are read from the
environment rather than `settings.py` because that file is orchestrator-owned:
`HEALTH_REQUIRED_DEPS` (default `db,broker,neo4j,object_store`) and
`CELERY_REQUIRE_STAGES` (default `1`).

## Make targets

```
make help                         list everything
make env                          .env from .env.example, secrets generated
make up / up-dev / up-gpu / up-obs / down / down-hard / logs / ps / health
make migrate                      make bootstrap        make reset-db
make test / test-api / test-web / test-integration
make lint / fmt / openapi         make seed             make warm-models
make worktrees SPRINT=3 SLUG=…    make ci-up / ci-smoke / ci-down
make revision m="…"               ORCHESTRATOR ONLY — typed confirmation
```

## Gotchas

- **Neo4j takes ~20s to accept connections** after container start; its
  healthcheck carries a 40s `start_period`. Retry on `ServiceUnavailable`.
- **`proxy_buffering off`** in `web/nginx.conf` or SSE streaming silently hangs.
  Also `chunked_transfer_encoding off` and a 3600s read timeout.
- **Models are volume-mounted, not baked.** `make warm-models` fills the shared
  `/models` volume once, behind an flock so two worktrees cannot race. **Done
  for Sprint 1** — the `traverse_model_cache` volume is warm (Docling 1.3G,
  BGE-M3 2.6G); confirmed `SentenceTransformer("BAAI/bge-m3")` loads with
  `HF_HUB_OFFLINE=1` and no network. Do not run `download_models()` again.
- **Tests must not hit the network** — `MODELS_OFFLINE=1` sets `HF_HUB_OFFLINE`
  and `TRANSFORMERS_OFFLINE` and points Docling at `/models/docling`.
- **`ruff format` ignores `per-file-ignores`.** The migrations are excluded with
  `--exclude db/migrations` in CI and `make lint`; without it the four
  pre-existing migrations fail a check the lint config exempts them from.
- **`docker compose ps` hides exited containers.** `scripts/wait_for_healthy.sh`
  uses `ps -a`, or the one-shot services look absent forever.
- **`%2F` in an AMQP URL.** `pyamqp://…/%2Fbe1` is vhost `/be1`; `…/be1` is a
  different vhost that does not exist.
- **RabbitMQ 4 denies `transient_nonexcl_queues` by default.** Celery's pidbox
  and reply queues are declared `durable=false exclusive=false`, and with the
  feature denied the worker crashloops within a second of boot
  (`amqp.exceptions.InternalError: (541) INTERNAL_ERROR`,
  `RestartFreqExceeded`). Fixed by mounting
  `docker/rabbitmq/rabbitmq.conf` (`deprecated_features.permit.*`) into
  `/etc/rabbitmq/conf.d/`. If a worker crashloops on boot with that traceback,
  check the broker has this file mounted before looking anywhere else.
- **SQLAlchemy's native `Enum` column stores the Python member NAME, not its
  `.value`.** `project.kind` in Postgres holds the literal string
  `'STANDALONE'`, not `ProjectKind.STANDALONE.value` (`'standalone'`). Bites
  anyone hand-seeding a row with raw SQL (`docker compose exec db psql`) —
  found while writing `scripts/test_integration_ingestion.py` (S2.18).
- Langfuse needs a **dedicated Postgres** — it runs its own Prisma migrations.
- vLLM under WSL2 in compose may not start — the documented fallback is
  `INFERENCE_MODE=api`, which is the default, so nobody is blocked on a GPU.

## Related

[llm-runtime.md](llm-runtime.md) · [BRANCH.md](../../../BRANCH.md) §4, §9 ·
[plans/sprint-1/devops-1.md](../../../plans/sprint-1/devops-1.md) ·
[plans/sprint-1/HANDOFF.md](../../../plans/sprint-1/HANDOFF.md)

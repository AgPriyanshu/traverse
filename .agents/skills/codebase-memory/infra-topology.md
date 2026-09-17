# Infra topology

What runs where, and how four agents share one machine. Symbols over line
numbers.

## Current state

**Built:** `api/docker-compose.yml` with three services — `db`
(pgvector/pg18), `neo4j` (5-community), `vllm` (Qwen3-8B-AWQ, GPU). Volumes
`postgres_data`, `neo4j_data`.

**Not built:** RabbitMQ (despite Celery pointing at
`pyamqp://user:password@localhost:5672` — nothing serves that address), the API
service, the Celery worker, the web service, MinIO, Langfuse, the migration
runner, healthchecks, profiles, `Makefile`, `.env.example`, CI. All S1.

The compose file also moves to the repo root in S1 so it can build both `api/`
and `web/`.

## Planned services (S1)

| Service | Image / build | Note |
| --- | --- | --- |
| `db` | `pgvector/pgvector:pg18-trixie` | port 5433 |
| `neo4j` | `neo4j:5-community-trixie` | 7474 / 7687 — **single database only** |
| `rabbitmq` | `rabbitmq:4-management` | vhosts `/be1`, `/be2`, `/int` |
| `api` | `api/Dockerfile` | uvicorn :8000 |
| `celery-worker` | same image | `--concurrency=2` |
| `web` | `web/Dockerfile` | nginx; Vite in dev profile |
| `minio` | `minio/minio` | PDFs + page renders |
| `langfuse` | `langfuse/` | **its own Postgres**, not the app DB |
| `migrate` | api image | one-shot `alembic upgrade head`, gates `api` and worker |
| `vllm` | `vllm/vllm-openai` | GPU profile only |

## Profiles

| Profile | Contents |
| --- | --- |
| `default` | everything except vLLM; `INFERENCE_MODE=api` |
| `gpu` | adds vLLM; `INFERENCE_MODE=local` |
| `dev` | hot-reload API + Vite dev server, source bind-mounted, Flower |
| `ci` | Postgres + RabbitMQ only, no models |

The demo must run on a machine with no GPU (PRD NFR-deploy), so `default`
excludes vLLM by design.

## Agent isolation

Infra containers are **host singletons** started once from the integration
checkout. Isolation is at the database and port level, not the container level.

| Resource | Isolation |
| --- | --- |
| Postgres | `traverse_be1`, `traverse_be2`, `traverse_int` (`scripts/bootstrap_databases.sh`) |
| Neo4j | **be2 exclusive** — Community edition is single-database |
| RabbitMQ | vhost per agent |
| MinIO | bucket per agent |
| vLLM | **shared** — one GPU. Timings from a worktree are invalid. |
| FastAPI | 8000 int · 8001 be1 · 8002 be2 · 8003 fe1-mock |
| Vite | 5173 fe1 · 5174 int |

Each worktree writes its own `api/.env` from `.env.example`. `.env` is
gitignored and must never be committed.

## Healthchecks that assert behaviour

| Service | Check |
| --- | --- |
| `db` | `pg_isready` **and** `SELECT 1 FROM pg_extension WHERE extname='vector'` |
| `neo4j` | `cypher-shell "RETURN 1"` |
| `api` | `/health` with per-dependency status, not a bare 200 |
| `celery-worker` | `celery inspect ping` **plus** all 8 frozen task names in `inspect registered` |
| `vllm` | `GET /v1/models` |

Everything dependent uses `depends_on: {condition: service_healthy}`.

## Make targets (S1)

```
make up / down / logs / ps        make migrate        make seed
make test / test-integration      make reset-db       make warm-models
make shell-api / shell-db / shell-neo4j
make worktrees                    make graph-rebuild BOOK=<id>
make revision m="..."             ORCHESTRATOR ONLY
```

## Gotchas

- **Neo4j takes ~20s to accept connections** after container start. Retry on
  `ServiceUnavailable` with backoff; every agent hits this.
- **`proxy_buffering off`** in nginx or SSE streaming silently hangs. Set in S1
  with a comment saying why.
- **Models are volume-mounted, not baked.** An image with BGE-M3 inside is ~4 GB.
  `make warm-models` fills the shared volume once.
- **Tests must not hit the network** — `MODELS_OFFLINE=1` sets `HF_HUB_OFFLINE`
  and Docling's `artifacts_path`.
- Never let two agents run Docling's `download_models()` concurrently.
- Langfuse needs a **dedicated Postgres**; sharing the app DB causes schema
  conflicts.
- vLLM under WSL2 in compose may not start — the documented fallback is
  `INFERENCE_MODE=api` so nobody is blocked on a GPU.

## Related

[llm-runtime.md](llm-runtime.md) · [BRANCH.md](../../../BRANCH.md) §4, §9 ·
[plans/sprint-1/devops-1.md](../../../plans/sprint-1/devops-1.md)

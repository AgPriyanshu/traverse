# Sprint 1 · DevOps Engineer 1

**Branch:** `ai/do1/sprint-1-foundations` · **Worktree:** `../traverse-wt/do1`
**Read first:** [BRANCH.md](../../BRANCH.md), [sprint-1/README.md](README.md)

## Mission

`docker compose up` must produce a working system. Today the compose file has
three services (Postgres, Neo4j, vLLM), no API, no worker, no broker despite
Celery pointing at `pyamqp://user:password@localhost:5672` — an address nothing
serves. This sprint delivers the full topology, healthchecks that mean
something, one-command developer ergonomics, and CI. You are the first merge in
every train, so your work has to be the most stable.

**PRD refs:** NFR-deploy (cold start < 5 min), NFR-obs, Phase 1.5

## Owned paths

```
docker-compose.yml  docker-compose.*.yml  docker/**
api/Dockerfile  web/Dockerfile  web/nginx.conf  **/.dockerignore
Makefile  .env.example  scripts/**  .github/workflows/**  api/ops/**
```

Forbidden: `api/pipeline/**`, `api/graph/**`, `api/query/**`, `web/src/**`.

---

## S1.11 — Complete the compose topology

Add to the existing file (keep Postgres, Neo4j, vLLM as-is; they work):

| Service | Image / build | Notes |
|---|---|---|
| `rabbitmq` | `rabbitmq:4-management` | vhosts `/be1`, `/be2`, `/int` created at boot (BRANCH.md §4) |
| `api` | build `api/Dockerfile` | uvicorn, `:8000`, hot-reload in dev profile |
| `celery-worker` | same image, different command | `--concurrency=2`, own healthcheck |
| `web` | build `web/Dockerfile` | nginx serving the Vite build; dev profile runs Vite instead |
| `minio` | `minio/minio` | bucket auto-create via a one-shot `mc` init container |
| `langfuse` | per the existing `langfuse/` directory | plus its own Postgres — do **not** share the app DB |
| `migrate` | api image, `alembic upgrade head` | one-shot, `restart: no`, gates `api` and `celery-worker` |

**Profiles** (PRD NFR-deploy — the demo must run on a machine with no GPU):

- `default` — everything except vLLM; `INFERENCE_MODE=api`
- `gpu` — adds vLLM; `INFERENCE_MODE=local`
- `dev` — hot-reload API and Vite dev server, source bind-mounted
- `ci` — Postgres + RabbitMQ only, no models

*Acceptance:* `docker compose up` on a GPU-less machine reaches all-healthy.
`docker compose --profile gpu up` adds vLLM and flips inference mode with no
other change.

## S1.12 — Dockerfiles and healthchecks

**`api/Dockerfile`** — multi-stage: `uv sync --frozen` into a venv layer, then a
slim runtime. Non-root user. Layer ordering that keeps `uv sync` cached when
only source changes. Docling and BGE-M3 caches at `/models`, volume-mounted, not
baked (an image with BGE-M3 inside is ~4 GB and murders the clone story).

**`web/Dockerfile`** — `pnpm build` → nginx:alpine. `nginx.conf` proxies
`/api` → `api:8000`, enables SSE passthrough (`proxy_buffering off` — **without
this, Sprint 6's streaming answers silently hang**, so set it now and leave a
comment saying why), and serves SPA fallback to `index.html`.

**Healthchecks that assert behaviour, not liveness:**

| Service | Check |
|---|---|
| `db` | `pg_isready` **and** `SELECT 1 FROM pg_extension WHERE extname='vector'` |
| `neo4j` | `cypher-shell "RETURN 1"` |
| `rabbitmq` | `rabbitmq-diagnostics check_running` |
| `api` | `GET /health` returning per-dependency status, not a bare 200 |
| `celery-worker` | `celery inspect ping` **plus** all 8 frozen task names present in `inspect registered` |
| `vllm` | `GET /v1/models` |
| `minio` | `mc ready local` |

Every dependent service uses `depends_on: {condition: service_healthy}`. A
worker that starts before Postgres and dies is a five-minute debugging tax paid
once per agent per day.

Ask BE1 to expose `/health` with dependency detail — it is their route file.
File it as a HANDOFF item on Day 2, not Day 5.

## S1.13 — Developer ergonomics

**`Makefile`:**

```
make up / down / logs / ps
make migrate              alembic upgrade head in the api container
make revision m="..."     ORCHESTRATOR ONLY — prints a loud warning to agents
make shell-api / shell-db / shell-neo4j
make test                 backend + frontend
make test-integration     the merge-train gate
make seed                 load the public-domain corpus (grows from Sprint 2)
make reset-db             drop, recreate, migrate, seed
make worktrees            create the four agent worktrees for a new sprint
make warm-models          pre-download Docling + BGE-M3 into the shared volume
```

**`.env.example`** — every settings key from the freeze, documented inline, with
working local defaults and obvious placeholders for secrets. `.env` stays
gitignored; verify no `.env` is currently tracked.

**`scripts/bootstrap_databases.sh`** — creates `traverse_be1`, `traverse_be2`,
`traverse_int`, each with the `vector` extension, plus the three RabbitMQ
vhosts and three MinIO buckets. Idempotent. This is the script that makes
BRANCH.md §4 real.

## S1.14 — CI

`.github/workflows/ci.yml`, on every push and PR:

1. `ruff check` + `ruff format --check` on `api/`
2. `uv run pytest api/tests -q` against a Postgres service container (`ci` profile)
3. `pnpm oxlint` + `pnpm tsc --noEmit` on `web/`
4. `pnpm build` — a type-clean app that fails to build is still broken
5. **OpenAPI drift check** — boot the API, regenerate `schema.d.ts`, fail on diff
6. Compose smoke test — `docker compose --profile ci up -d`, wait for healthy,
   `curl /health`, tear down

Under 6 minutes total, or agents will stop waiting for it. Cache `uv` and
`pnpm` stores aggressively.

## S1.15 — Model cache warm-up

`make warm-models` downloads Docling layout/OCR models and BGE-M3 into a named
volume shared by `api` and `celery-worker`. Run once; never again.

**Tests must not hit the network** (BE1 will raise this). Provide a
`MODELS_OFFLINE=1` env that sets `HF_HUB_OFFLINE=1` and Docling's
`artifacts_path` at the volume, and make CI use it after a cache-restore step.

---

## Definition of Done

- [ ] Cold `docker compose up` → all-healthy in under 5 minutes on a warm cache
- [ ] Works with **and** without a GPU via profiles
- [ ] `bootstrap_databases.sh` gives every agent an isolated slice
- [ ] CI green and under 6 minutes
- [ ] No secret, no `.env`, no absolute host path committed
- [ ] `HANDOFF.md`: service names, ports, env var names, `make` targets

## Escalate immediately if

- Langfuse self-hosting needs a schema or version the app Postgres conflicts
  with → give it a dedicated Postgres, do not share
- vLLM cannot start under WSL2 in compose → document the host-side fallback and
  make `INFERENCE_MODE=api` the default so nobody is blocked on a GPU

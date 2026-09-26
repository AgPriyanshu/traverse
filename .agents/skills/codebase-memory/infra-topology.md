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

**Built (S3):** `scripts/seed_corpus.py`'s chapter-heading gap is **fixed**
(SCR-1, `plans/sprint-3/SCR.md`) — a chapter heading now renders in 16pt
`Courier-Bold` instead of the same 10pt/regular font as body text, which
crosses the threshold (empirically ~1.4x body size) where Docling's layout
model emits `SECTION_HEADER` instead of `TEXT`. Verified directly against the
installed model, both on a synthetic probe and on the real regenerated
`corpus/downloads/pride-and-prejudice.pdf` (`CHAPTER III.`/`CHAPTER IV.`
labelled `section_header`). `paginate()`'s line-to-page assignment is
unchanged by this — only `pdf_sha256` moved; page counts are identical to
before. `eval/**` (new, do1-owned): `eval/schema/roster.schema.json`,
`eval/gold/{pride_and_prejudice,wuthering_heights}/roster.yaml` (S3.13, pinned
to the regenerated corpus's checksums), `eval/metrics.py` (roster P/R/F1,
a real B³ implementation verified against a hand-computed toy example,
tier accuracy, rejection precision, cascade-stage contribution),
`eval/loaders.py` (schema + checksum-pinning enforcement — a repaginated
corpus fails loudly), `eval/runners/extraction.py` (PR-comment markdown
renderer), `scripts/label_roster.py` (terminal review tool, reused for
Sprint 8's question set). `api/ops/extraction_quality.py` and
`api/ops/extraction_cost.py` (S3.14/S3.15) wire `eval/metrics.py` against the
real `Character`/`CharacterAppearance`/`CharacterMention`/`RejectedCandidate`
tables, behind two new do1-owned routes: `GET /ops/extraction-quality` and
`GET /ops/extraction-cost` (both `?book_id=`, response models defined
locally rather than in the frozen `api/contracts/api.py` — see SCR-2).
`api/ops/vllm_metrics.py` scrapes vLLM's own Prometheus `/metrics` for
prefix-cache hit rate and KV-cache usage; `GET /ops/metrics`'s
`prefix_cache_hit_rate` field (frozen since S2.17, previously always `None`)
is now populated live from it when `INFERENCE_MODE=local`.
`.github/workflows/extraction-quality.yml` (new) runs the one-novel reduced
set on PRs touching `api/extraction/**`; `scripts/nightly_corpus_ingestion.py`
(S2.18) extended to also post extraction quality/cost for gold-labelled books
alongside its existing wall-clock/cost report.

**Broken / partial:** the Sprint 1 `api/llm.py` `CACHE_DIR` absolute-path
defect is gone — fixed by the Sprint 2 contract freeze (`3cdc9fb`), confirmed
by `grep -rn "/home/" .` returning nothing outside `.gitignore`d files.
`make test-integration`'s <8-minute budget is unverified end to end (tearing
down the shared singleton stack to time it would have disrupted every other
worktree mid-sprint — see HANDOFF.md). The nightly corpus job's wall clock is
API-inference, not the local-vLLM number NFR-perf is judged on (no GPU on
`ubuntu-latest`). `.github/workflows/extraction-quality.yml` and
`scripts/pr_extraction_quality.py` are unverified end to end on a real GitHub
Actions run and against real `api/extraction/**` output — be1's pass 1 had
not merged as of this writing, so the closest available check was confirming
the script's HTTP/DB-adjacent logic and lint/unit tests pass; see HANDOFF.md.

**Built (S4, do1):** `eval/relation_metrics.py`, `eval/schema/relations.schema.json`,
`eval/gold/pride_and_prejudice/relations.yaml`, `eval/runners/relations.py`,
`api/ops/relation_quality.py` + `relation_cost.py` behind `GET /ops/relation-quality`
and `/ops/relation-cost`, `api/ops/graph_rebuild.py` + `graph_fixture.py` (the
drill), `scripts/ingest_book.py`, `scripts/judge_citations.py`,
`.github/workflows/relation-quality.yml`. Make targets: `ingest`, `graph-rebuild`,
`graph-rebuild-drill`, `eval-relations`, `judge-citations`, `docker-nocreds`.
S4.15 root-caused the prefix-cache-hit-rate shortfall against a real run and
raised the vLLM `vllm` service's `--gpu-memory-utilization` `0.75` → `0.85`
(+39% KV-cache budget on the 12GB card); see llm-runtime.md's "Serving" and
"Gotchas" for the numbers and why 80% is a structural ceiling for this book's
roster:chunk ratio, not purely a config problem. Also wired
`api/ops/vllm_metrics.py`'s previously-dead `hit_rate_between`/
`fetch_vllm_cache_counters` into `scripts/ingest_book.py` and
`scripts/nightly_corpus_ingestion.py` — the ops endpoints' own
`prefix_cache_hit_rate` field is vLLM's lifetime-cumulative average since
last boot, not scoped to a book or run.

**Not built:** anything Sprint 5+.

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
| Postgres (test) | `traverse_test` — **not** one of the three slices above, belongs to the `test` compose service, truncated between runs |
| Postgres (default) | the `db` container's own `postgres` database, migrated by the plain `migrate` service. `docker compose down -v` wipes this **and every database above** — the integration checkout's `traverse_int` is not a separate volume from an agent's, just a separate database in it |
| Neo4j | **be2 exclusive** — Community edition is single-database |
| RabbitMQ | vhost per agent: `/be1`, `/be2`, `/int` |
| MinIO | bucket per agent, plus `traverse-test` (SCR-19 root cause) for the `test` service — same reasoning as Postgres's `traverse_test` row above |
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
make ci-up-extraction             S3.14: ci-up's subset + MinIO, for a real book upload
make revision m="…"               ORCHESTRATOR ONLY — typed confirmation
```

## Gotchas

- **`error getting credentials` on any image build.** Docker Desktop's WSL
  helper (`credsStore: desktop.exe`) fails even for public images. The
  Makefile detects that and exports `DOCKER_CONFIG=$PWD/.docker-nocreds` (a dir
  holding `{}`); force with `NOCREDS=1`. Outside make: `make docker-nocreds`
  prints the export line.
- **`test` image is tagged per worktree** (`traverse-api-test:$TEST_IMAGE_TAG`).
  Bare `docker compose` without it falls back to `dev`, shared across worktrees.
- **`docker compose run` from a worktree can recreate the shared db/rabbitmq**
  when the compose config differs from the running stack. Volumes survive.

- **`eval/` is a repo-root package, not under `api/`, and `api/ops/
  extraction_quality.py`/`extraction_cost.py` import it anyway.** Works via
  `PYTHONPATH=/app` (same trick that makes `import api...` work) — `api/
  Dockerfile`'s runtime stage `COPY`s `eval/` and just `corpus/manifest.json`
  (not `corpus/downloads/`, gitignored and multi-hundred-MB) into the image.
  If a third do1-owned module starts importing `eval.*`, it already works;
  if a new top-level dir needs the same trick, copy it the same way.
- **`api/tests/pipeline/test_books_routes.py`'s exact `len(paths) == 34`
  frozen-count assertion breaks on any agent's legitimate new route** —
  be2's S3.6/S3.7 routes will hit this exactly the same way do1's two new
  S3.14/S3.15 `/ops/*` routes did (SCR-3, `plans/sprint-3/SCR.md`). Not a
  regression to chase if you see it; check whether an SCR already covers the
  new count before assuming your branch broke something.
- **Neo4j takes ~20s to accept connections** after container start; its
  healthcheck carries a 40s `start_period`. Retry on `ServiceUnavailable`.
- **`proxy_buffering off`** in `web/nginx.conf` or SSE streaming silently hangs.
  Also `chunked_transfer_encoding off` and a 3600s read timeout.
- **Models are volume-mounted, not baked.** `make warm-models` fills the shared
  `/models` volume once, behind an flock so two worktrees cannot race. Do not
  run `download_models()` again once it's warm.
- **`SENTENCE_TRANSFORMERS_HOME` and `HF_HOME` are separate cache roots.**
  `SentenceTransformer(model_id)` only fills the former; a plain
  `transformers.AutoTokenizer.from_pretrained(model_id)` (chunking.py's token
  counting, `api/llm/budget.py`'s) only ever looks in the latter and re-hits
  the network under `MODELS_OFFLINE=1` even though the same model's weights
  already sit on disk under the other root. `scripts/warm_models.py` warms
  both the embedding model's tokenizer and `settings.llm_model`'s (S2.18
  merge-train fix) — if a third module starts tokenizing a model neither of
  those two warms, add it there rather than assuming "it's already cached."
- **The `test` service shared the live MinIO bucket with `api`/`celery-worker`
  — root cause of SCR-19.** Unlike Postgres, `MINIO_BUCKET` had no
  `test`-service override — the `test` service inherited `${MINIO_BUCKET:-
  traverse-int}` from `&api-env` untouched, so `api/tests/pipeline/
  test_books_routes.py`'s `client()` fixture teardown (`await
  store.delete_prefix("books/")`, run after **every** test) was deleting the
  live demo books' source PDFs and rendered pages on every
  `docker compose --profile test run --rm test`. fe1 found the symptom
  (page-image requests 500ing for both demo books, SCR-19) without knowing the
  cause; the actual deletions had already happened by the time it was traced.
  Fixed the same way `traverse_test` isolates Postgres: `traverse-test` is now
  its own bucket, in `MINIO_BUCKETS` (three copies, see the `AGENT_DATABASES`
  entry below — `.env.example`, `docker-compose.yml`'s `minio-init` default,
  `docker/minio/init-buckets.sh`'s own fallback default — plus a fourth,
  `scripts/bootstrap_databases.sh`, which builds its own bucket list rather
  than reading the shared default and needed the same edit for an
  already-running cluster). The `test` service now overrides `MINIO_BUCKET:
  ${TEST_MINIO_BUCKET:-traverse-test}`, mirroring `TEST_POSTGRES_DB`. Neo4j was
  checked for the same class of bug and is **not** affected: it has no
  per-service override (Community edition is single-database, so it can't),
  but `api/tests/graph/conftest.py`'s `clean_project` fixture scopes every
  test to a fresh random `project_id` and `projection.reset_project()` only
  ever deletes nodes matching that one project id — it was never a blanket
  prefix delete like MinIO's, so sharing the live database is safe by
  construction. If a fifth resource gets a `test`-service override in
  `&api-env`, check whether its test teardown does an unscoped delete before
  assuming isolation is unnecessary.
- **`AGENT_DATABASES` has three copies that must agree**: `.env.example`,
  `docker-compose.yml`'s inline default, and
  `docker/postgres/init/10-agent-databases.sh`'s own fallback default. Only
  `.env.example` listed `traverse_test`; the other two didn't, so a genuinely
  fresh Postgres volume (no personal `.env`, or `docker compose down -v`)
  never created it and `migrate-test` failed outright — invisible unless
  something actually wipes volumes rather than just restarting containers
  (found running Sprint 2's merge-train gate cold, not by any per-agent
  test). If you add a database to one of these three, add it to all three.
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

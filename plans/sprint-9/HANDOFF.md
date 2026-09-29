# Sprint 9 · do1 handoff

Everything below is what another agent, or a human doing the actual go-live,
needs from do1's five stories (S9.1-S9.5). Written alongside the code, not
after — see AGENTS.md's "read the memory" protocol for why that matters.

## S9.1-S9.3 — new `/ops/*` routes (for fe1's S9.10 dashboard)

| Route | Contract | Notes |
| --- | --- | --- |
| `GET /ops/cost-breakdown?window=daily\|monthly&persist=` | `CostBreakdown` | Rolling cost by stage and by purpose, live-computed. `persist=true` also writes a `cost_snapshot` row. |
| `GET /ops/cost-snapshots?limit=` | `list[CostBreakdown]` | Stored history, newest first — the chart's feed. Empty until something calls `cost-breakdown?persist=true` at least once; nothing schedules that yet (see "Not built" below). |
| `GET /ops/performance?book_id=` | `PerformanceOut` (local, `api/ops/performance_telemetry.py`) | Stage latency percentiles, parse-stage pages/min, prefix-cache hit rate + KV usage (local inference only), Celery queue depth. |
| `GET /ops/pipeline-health?book_id=&limit=` | `PipelineHealthOut` (local, `api/ops/pipeline_health.py`) | Run history (each with `trace_url`), per-stage failure rate, retry outcomes, dead-letter list. |
| `GET /ops/budget-status` | `BudgetStatusOut` (local, `api/ops/budget_guard.py`) | Monthly spend vs. `MONTHLY_BUDGET_USD` (env, default 50). |

`PerformanceOut`/`PipelineHealthOut`/`BudgetStatusOut` are locally-defined
response models, not in the frozen `api/contracts/api.py` — same pattern as
`ExtractionCostOut`/`ReviewMetricsOut` from earlier sprints (SCR-2/SCR-3
precedent, `plans/sprint-3/SCR.md`). No SCR filed this sprint since it's
additive and doesn't touch a frozen file.

**Not built:** nothing schedules `cost-breakdown?persist=true` on a cadence
(a daily cron / Celery beat tick). `/ops/cost-snapshots` will read empty
until either a human hits the endpoint with `persist=true` periodically, or
a future story wires a scheduler. Flagging this now rather than silently —
do1 has no owned scheduler primitive yet (`api/tasks.py` is orchestrator-
owned; a Celery beat entry is a schema-adjacent change).

**Known gap, not fixed this sprint:** `/ops/performance`'s queue depth is
`celery inspect active/reserved/scheduled` — what workers *currently hold*,
not a true broker-side backlog. RabbitMQ's own management HTTP API
(`RABBITMQ_MGMT_PORT`, already exposed in `docker-compose.yml`) would give
the real unclaimed-message count per queue; not wired up this sprint for
lack of time, and `reachable=False` is honest about not being that number
rather than silently wrong.

## S9.4 — public deploy tooling (NOT executed publicly)

**Built, real, tested:**

- `docker-compose.prod.yml` — CPU-only inference (`INFERENCE_MODE=api`,
  no `gpu` profile — already the default profile's behaviour, this overlay
  just makes it explicit), CPU/memory `deploy.resources.limits` on
  `api`/`celery-worker`, and a new `edge` service.
- `docker/nginx/edge.conf` — TLS termination, per-IP rate limiting
  (`limit_req_zone`, 5r/s general + 2r/min on `/api/books` uploads, both
  `limit_req_status 429`), and a `proxy_cache` zone in front of
  `/api/books/*/pages/*` (the honest, buildable stand-in for "a CDN in front
  of page renders" — see below for what a real CDN would replace it with).
- `scripts/gen_self_signed_cert.sh` — local-only TLS cert for verification.
- `scripts/budget_monitor.py` / `api/ops/budget_guard.py` — reads
  `MONTHLY_BUDGET_USD` (env, default $50), and on breach runs
  `docker compose stop celery-worker` so ingestion pauses (API stays up,
  serving what's already ingested) rather than the bill running away.
  `make budget-check` (`--no-act` reports only).
- `scripts/verify_prod_deploy.py` — the local smoke test described below.

**Verified for real, in this session:**

- `docker compose -f docker-compose.yml -f docker-compose.prod.yml config`
  parses and merges cleanly (project-scoped volumes, no `gpu` profile pulled
  in, CPU-only env as expected).
- `docker/nginx/edge.conf` passes `nginx -t` and was run standalone (a real
  nginx container, a dummy upstream aliased as `web`, no app stack involved)
  against `scripts/gen_self_signed_cert.sh`'s cert: **TLS terminates** (200
  over HTTPS), **HTTP redirects to HTTPS** (301), and **rate limiting trips**
  under a 40-request burst (`429`, after the `limit_req_status 429` fix —
  nginx's own default is 503, which is not the semantically correct code and
  is also what `scripts/verify_prod_deploy.py` checks for).

**NOT executed, and why:**

- `make up-prod` (the full overlay against real `api`/`db`/`celery-worker`)
  was **not** run end to end on this shared host. Its default ports
  (`API_PORT=8000`, `POSTGRES_PORT=5433`, `MINIO_PORT=9002`, etc.) collide
  with the already-running shared integration stack every other agent's
  worktree depends on (BRANCH.md §9's documented singleton-stack
  contention — the same reasoning `infra-topology.md` already gives for why
  `make test-integration`'s wall-clock budget is unverified end to end).
  Spinning up a second full Postgres/RabbitMQ/MinIO/Neo4j stack side by side
  would also have meaningfully loaded a host three other agents were
  actively using during this session (observed: the shared `db`/`rabbitmq`
  containers were recreated and briefly unreachable multiple times purely
  from other agents' own work, independent of anything here).
- **No public deployment was executed or attempted** — no cloud account, no
  domain, no DNS record, no firewall rule, no real TLS certificate. This was
  an explicit constraint on this story (BRANCH.md, the sprint brief): prove
  the deploy path works, do not go live.

### What a human does to actually go live

1. **Host.** Provision a CPU-only VM (no GPU needed — `INFERENCE_MODE=api`
   is already the default). 2 vCPU / 4GB RAM covers `api` + `celery-worker`
   + `db` + `rabbitmq` + `minio` + `web` + `edge` at demo traffic; scale up
   only if the ops dashboard's own `/ops/performance` shows queue depth
   climbing under real load.
2. **Domain + DNS.** Buy/point a domain's `A`/`AAAA` record at the host.
3. **Real TLS.** Replace `scripts/gen_self_signed_cert.sh`'s output with a
   real certificate — either run `certbot` (webroot or DNS-01 challenge)
   on the host and mount its `/etc/letsencrypt/live/<domain>/` output at
   `docker/nginx/certs/edge.{crt,key}` in place of the self-signed pair, or
   terminate TLS one layer up (a managed load balancer / Cloudflare in front
   of the host) and let `edge` speak plain HTTP behind it. Either way,
   update `ssl_certificate`/`ssl_certificate_key` in `docker/nginx/edge.conf`
   if the paths change, and set up a renewal cron (`certbot renew`, twice
   daily, is idempotent and free).
4. **Firewall.** Only 443 (and 80, for the redirect) reach the internet.
   `docker-compose.prod.yml` already binds `api`/`web`'s own ports to
   `127.0.0.1` so they are unreachable directly even without a host
   firewall, but add one anyway (cloud security group / `ufw`) as
   defence in depth — compose's port publishing is not a substitute for it.
5. **Real CDN (optional, if page-render traffic justifies it).** Put
   Cloudflare (or equivalent) in front of the domain with caching enabled
   for the `/api/books/*/pages/*` path pattern; `edge.conf`'s own
   `proxy_cache` already does this at one hop, a real CDN adds
   geographic edge points, which the docker-based stand-in cannot.
6. **Budget cap.** Set a real `MONTHLY_BUDGET_USD` in the host's `.env`
   (not the default $50 placeholder) and put `scripts/budget_monitor.py
   --interval 300` behind a systemd timer or cron, or a long-running
   supervisor process, so a stuck ingestion loop can't run up an unbounded
   frontier-API bill unattended.
7. **Upload sweep.** Cron `make upload-sweep` hourly (or a systemd timer)
   so expired demo uploads (24h TTL) actually get deleted — nothing
   schedules `scripts/sweep_upload_sessions.py` on its own yet.
8. **Seed the public corpus.** `make seed && make ingest-series ...` (or the
   individual `make ingest BOOK=...`) against the production database before
   opening it up — the licence-enforcement half of S9.5 (public-domain-only
   guard on the *seeded* corpus, as opposed to *visitor uploads*, which this
   sprint's guard covers) is `scripts/seed_corpus.py`'s existing
   `corpus/LICENSES.md`-backed pinning (S2.16), not new code from this
   sprint.
9. Run `scripts/verify_prod_deploy.py` (with `EDGE_HTTP_PORT`/
   `EDGE_TLS_PORT` pointed at the real host) as the final go/no-go check
   before announcing the URL.

## S9.5 — integration points for be1 (S9.8, upload privacy/isolation)

`api/ops/upload_guard.py` is a library, not wired into any route (do1 does
not edit `api/routes/books.py`). What be1's upload route needs to call, in
order, on `POST /projects/{id}/books` (or wherever the visitor-upload
endpoint ends up):

1. `hash_ip(request.client.host)` → `ip_hash`.
2. `check_ip_rate_limit(session, ip_hash)` — raises `UploadQuotaExceeded`.
3. `start_upload_session(session, session_token=<cookie or header>, ip_hash=ip_hash)`
   → get-or-create the session row. `session_token` is whatever be1's S9.8
   isolation mechanism already uses to key a visitor's session; if none
   exists yet, a signed cookie is the simplest option and does not need a
   new frozen field.
4. `check_session_quota(upload_session)` — raises `UploadQuotaExceeded`.
5. `count_pdf_pages(file_bytes)` then `check_page_limit(page_count)` —
   raises `UploadTooLarge`. Do this **before** handing the file to the
   pipeline, not after — the whole point is not burning a GPU/API slot on a
   file that will be rejected anyway.
6. `check_public_domain(extracted_text_sample)` — does not raise; returns a
   `GuardResult(flagged, reasons)`. Product decision (not made by do1): a
   `flagged=True` result on a *visitor upload* should probably hard-reject
   (422) rather than warn, since ETH-1 is explicit about "reject a clearly
   copyrighted upload." A first-page text sample is enough; no need to scan
   the whole book.
7. After the book is accepted: `record_upload(session, upload_session, project_id=...)`.

All four exceptions (`UploadQuotaExceeded`, `UploadTooLarge` — both subclass
`UploadGuardError`) carry a human-readable `.args[0]`; map to HTTP 429/413
respectively. `sweep_expired_sessions` (via `make upload-sweep` / cron, see
above) is the only piece that touches storage/DB deletion — nothing in the
upload path itself deletes anything.

## Codebase-memory

`infra-topology.md` updated in the same commit as S9.4 (compose/edge/budget
additions) per BRANCH.md §10's Definition of Done.

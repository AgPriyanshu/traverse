# Sprint 9 — HANDOFF (be2)

## S9.6 — Routing policy engine (F7.3)

**What landed:** `GET`/`PUT /api/ops/routing-policy` replace the 501 stubs,
backed by the frozen `RoutingPolicy` table (migration `0012` — the README
above says `0014`, that's stale; the actual freeze commit is
`619208b`/`0012_routing_policy_cost_snapshot_upload_session.py`).

- **Append-only, never an update.** Every `PUT` inserts a new row
  (`version = max(version) + 1`); the live policy is always the max-version
  row. `api/llm/policy_repository.py::get_current_policy`/`write_new_policy`.
- **`GET` with no policy ever written** returns `version=0` plus
  `DEFAULT_PURPOSES` (today's implicit behaviour as a policy shape: every
  purpose → local, `judge` → `frontier_model` if one happens to be set) —
  never a 404 or an empty body, so a caller always has a well-defined
  "current policy" to read.
- **Live switching, same process, same session:** `PUT` installs the new
  policy into a process-global cache
  (`api/llm/routing.py::set_live_policy`/`get_live_policy`) *in addition to*
  persisting it, and `route_for` consults that cache before falling back to
  the static local default. The very next `structured_call` in the same API
  server process uses the new mapping — no restart, which is the PRD F7.3
  acceptance criterion.
- **Gap you should know about:** the cache is process-local and nothing
  loads it at startup. A fresh process (a server restart, a Celery worker)
  has no policy until *something* in it calls `GET`/`PUT` at least once.
  `GET` re-syncs the cache from Postgres specifically to paper over this for
  the dashboard's own read, but a Celery worker that never hits either route
  will silently keep routing on hardcoded defaults after a restart. If this
  matters for the demo, wire a startup hook (`api/main.py`'s lifespan) to
  call `get_current_policy` once and call `set_live_policy` — I didn't touch
  `api/main.py` since it's not in be2's owned paths this sprint and isn't
  clearly anyone's under `BRANCH.md`'s roster; flagging rather than guessing.
- **`query_log.policy_version`** is now populated
  (`api/query/pipeline.py::_finish`, reads `get_live_policy()` at answer
  time) — every query is attributable to the policy version that served it,
  which is what makes a cost/accuracy comparison across a flip
  interpretable. `query_log.model_used`/token/cost columns are **still
  unpopulated** — that's do1's cost-accounting territory (S9.1), not
  something this story touches.

**For fe1 (S9.10, the routing dashboard):**

- Read current policy: `GET /api/ops/routing-policy` → `{version, purposes}`
  (`purposes` keyed by the `LLMPurpose` enum's string values:
  `chapter_classify`, `character_extract`, `relation_extract`, `adjudicate`,
  `answer`, `judge`; values are model id strings, e.g.
  `"Qwen/Qwen3-8B-AWQ"` or a frontier model name).
- Flip it: `PUT /api/ops/routing-policy` with the full `purposes` dict (a
  partial dict *replaces* the whole live mapping — omitted purposes fall
  back to `DEFAULT_PURPOSES`' semantics, not their old policy value, since
  there's no partial-merge here). `version` in the request body is ignored;
  the server assigns it.
- **"What would this cost/score under an alternate policy" without flipping
  it for real:** I did not build a preview/dry-run endpoint — that felt like
  dashboard territory, not routing-mechanism territory, and there's already
  a mechanism to build it from: `api/ops/metrics.py::COST_TABLE`/
  `estimate_cost_usd(model, input_tokens, output_tokens)` (do1's, S2.17)
  maps a model id to a USD estimate. Pull a purpose's actual recent token
  usage (there isn't a clean per-purpose token breakdown exposed yet either
  — `QueryLog` doesn't carry tokens, see above) and re-run
  `estimate_cost_usd` against the alternate model name to preview a cost
  delta client-side, without ever calling `PUT`. **`COST_TABLE` only has an
  entry for the local model right now** (`api/ops/metrics.py`'s own comment:
  "add its entry here once [routing] lands rather than guessing at one
  now") — do1 needs to add a frontier model's real per-1M-token rate before
  a frontier cost preview means anything. For the accuracy half of the
  delta, `GET /api/ops/eval-runs/latest` (S8.8) is the existing "live eval
  accuracy" number; there's no per-policy-version slice of it yet, only
  per-ablation-cell.
- Unknown purpose keys in a `PUT` body get a `422`, not a silent drop.

## S9.7 — Frontier API path with fallback (§5.1)

**What landed:** `adjudicate`/`answer`/`judge` (`FRONTIER_ELIGIBLE_PURPOSES`,
`api/llm/routing.py`) can route to a real frontier model when
`settings.frontier_model` **and** `settings.frontier_api_key` are both set —
same `structured_call`/schema contract as local, no downstream branching on
provider. Two independent fallback layers, both to local vLLM:

1. **`route_for` itself** — asking for frontier (via `mode=api`, a live
   policy entry naming a non-local model, or `judge`'s own always-frontier
   default) with no usable key just resolves local instead of raising.
   `ModelRoute.fallback_reason` is set on the route so a caller — most of
   all the eval judge — can tell a degraded local grade apart from a real
   frontier one, rather than the two looking identical.
2. **`structured_call`'s circuit breaker** — if a frontier call actually
   *fails* transiently at runtime (network, 5xx, timeout — not merely
   unconfigured), it gets one immediate local retry before the
   `TransientLLMError` propagates. This exists because a query-path caller
   (the FastAPI request handler, not a Celery task) has no retry of its own
   for it — backend-2.md's own DoD: "a frontier outage must degrade, not
   fail."

**Residency floor, tightened, not loosened:** `settings.inference_mode ==
local` now blocks frontier routing for **every** purpose (before S9.7 this
check only ran for `judge`) — before this fix, a live policy entry naming a
frontier model could route `answer`/`adjudicate` externally even under an
explicit local-only setting, which is exactly the bypass NFR-residency/ETH-4
say must not exist. This check runs first, before `mode` or the live policy,
so neither an ablation sweep nor a `PUT` can route around it. **There is
still no per-book/per-project consent field** in the frozen Sprint 9
contracts — this global `settings.inference_mode` remains the only lever
there is. If per-upload consent (rather than a single host-wide switch) is
ever needed, that's a schema change (an SCR against `Book`/`Project` or a new
table), not something this sprint's contracts support.

**What is verified vs. not, and why (same honesty pattern as Sprint 8's
ablation work):**

- `settings.frontier_model`/`settings.frontier_api_key` are blank in this
  environment's `.env` by design — no key provisioned, and I did not try to
  provision one (I can't, and shouldn't).
- **Verified:** every branch of the fallback logic, with a fake/mocked
  frontier model and a fake/mocked API-connection failure —
  `api/tests/llm/test_routing.py` (residency floor, unconfigured-frontier
  fallback for judge/answer, live-policy-requested frontier still falling
  back without a key) and
  `api/tests/llm/test_structured.py::test_frontier_transient_failure_falls_back_to_local_once`
  (the circuit breaker, via a fake `get_llm` that raises
  `openai.APIConnectionError` when asked for a frontier model and returns a
  working fake otherwise).
- **Not verified, and cannot be from this environment:** a real frontier
  provider's actual latency, actual error shapes beyond what the `openai`
  SDK's exception hierarchy already models, rate-limit behaviour, and
  whether `ChatOpenAI(base_url=None, api_key=...)` against a real provider
  needs any provider-specific header/param this repo's `openai`-compatible
  client wrapper doesn't already send. A human supplying a real
  `FRONTIER_MODEL`/`FRONTIER_API_KEY` in `.env` and running one query through
  `/api/query` with `answer` policy-routed to frontier is the only way to
  close this gap. Nothing in this sprint's code depends on that verification
  happening — the fallback exists precisely so the demo works either way —
  but the "does the real integration work at all" question is open.

## Carryover fixes (flagged by Sprint 8's do1, both landed this sprint)

- **No request timeout anywhere in `api/llm`.** `api/llm/client.py::get_llm`
  now sets `timeout=60.0` (local) / `timeout=120.0` (frontier) on the
  `ChatOpenAI` instance. The `openai` SDK's `APITimeoutError` subclasses
  `APIConnectionError`, so this needed no change to
  `api/llm/errors.py::classify_call_error` — a timeout already lands as a
  retryable `TransientLLMError` once the deadline exists. Not covered by an
  automated test (there's no running server to actually time out against in
  this worktree, same GPU-singleton constraint as everything else in
  `api/llm`); reasoned about, not measured.
- **`greenlet_spawn has not been called` on every query route.** Root cause:
  `_finish` (`api/query/pipeline.py`) commits three times on the same
  request-scoped session (`write_query_log`, `record_turn`, `set_scope`),
  and that session defaults to `expire_on_commit=True`
  (`api/db/engine.py::get_session`) — every commit expires every ORM object
  the session holds, including the `Conversation` fetched earlier in the
  request. A later **synchronous** read of `conversation.id`/`.project_id`
  on an expired async-session object can't refresh itself outside an
  awaited call, which is exactly what SQLAlchemy's async extension raises
  that error for. Fixed by capturing `conversation.id`/`.project_id` into
  plain locals *before* the first commit, and threading those through
  instead of re-reading the ORM object (`api/query/conversation.py::set_scope`
  now takes an explicit `project_id` kwarg for the same reason, defaulting to
  reading it off `conversation` for a caller that knows its session hasn't
  committed since the object loaded — the existing unit test in
  `test_conversation.py` didn't need to change).
  **This class of bug only reproduces through the real HTTP route** — the
  root `api/tests/conftest.py`'s `session` fixture deliberately sets
  `expire_on_commit=False` to avoid it, which is exactly why
  `test_pipeline.py` (built on that fixture) never caught it despite
  exercising `_finish` directly. The regression test
  (`api/tests/query/test_answer_persistence_session.py`) goes through the
  real `client`/ASGI transport on purpose, with the router classifier
  stubbed to keep it offline.

## Test coverage added this sprint

`docker compose --profile test run --rm test pytest api/tests/llm
api/tests/query api/tests/ops api/tests/graph api/tests/relations
api/tests/review` — 277 passed, 1 pre-existing skip, on `traverse_test_be2`
after `alembic upgrade head` to `0012`.

## Files touched

`api/llm/routing.py`, `api/llm/client.py`, `api/llm/structured.py`,
`api/llm/policy_repository.py` (new), `api/routes/ops.py` (only the two
routing-policy handlers — everything else in that file is do1's),
`api/query/pipeline.py`, `api/query/conversation.py`,
`api/query/repository.py`, plus tests under `api/tests/llm/**`,
`api/tests/ops/test_routing_policy.py` (new — note: this lives outside
be2's normally-owned test paths, added because it's the direct counterpart
to the two carved-out routes; do1 should feel free to relocate it),
`api/tests/query/test_answer_persistence_session.py` (new). Codebase-memory
maps updated in the same commit: `llm-runtime.md`, `query-path.md`,
`data-model.md`.

No SCR filed — no schema change was needed beyond what the freeze already
landed.

# Sprint 9 — Handoff notes

## be1 — S9.8 Upload privacy (ETH-2)

**What landed:** `api/pipeline/session_privacy.py` — per-session upload
isolation and real deletion, wired into every route in `api/routes/books.py`.
Summary (full detail in `.agents/skills/codebase-memory/ingestion-pipeline.md`
§"Upload privacy"):

- `POST /projects` links the new project 1:1 to the caller's `UploadSession`
  (migration 0012); the response returns the session token in an
  `X-Session-Token` header (minted fresh if the caller sent none).
- Every book- and project-scoped route enforces ownership: a project with a
  live `UploadSession` 404s for anyone but the matching token; a project with
  no owning session (the seeded public corpus) stays open to everyone,
  unchanged from before this story.
- `content_hash`'s uniqueness is install-wide (frozen schema) but reuse is
  now project-scoped — a duplicate upload against a *different* project is a
  `409`, never silently pooled into someone else's project.
- `DELETE /books/{id}` is real: Postgres cascade (raw `DELETE`, not
  `session.delete()` — see the map for why), MinIO prefix delete, a
  best-effort Langfuse trace purge, and a call into be2's
  `api.graph.cascade.remove_book` / `api.graph.projection.reset_project` for
  the Neo4j side. Project + its `UploadSession` are deleted too once its last
  book is gone.
- 24h TTL sweep: `pipeline.sweep_expired_upload_sessions` is a registered
  Celery task with a `celery_app.conf.beat_schedule` entry set from
  `api/pipeline/tasks.py` (be1-owned; never edited `api/tasks.py` or
  `docker-compose.yml`).

**Two things the next steps need, for do1 / integration:**

1. **No `celery beat` service exists in `docker-compose.yml` yet.** The sweep
   task and its schedule entry are real and unit-tested, but nothing invokes
   Celery's beat scheduler in this compose file today, so the entry is inert
   until one is added — a one-line service (`celery -A api.workers.app beat`)
   sharing the existing worker's image/env. Alternatively, a cron-style
   trigger from `scripts/**` calling `celery_app.send_task("pipeline.sweep_expired_upload_sessions")`
   works without a beat process at all. Either is do1's call (docker-compose.yml
   and scripts/** are do1-owned).
2. **Live-Neo4j verification of the delete cascade is still owed at
   integration.** be1's own test suite (`api/tests/pipeline/test_session_privacy.py`)
   monkeypatches `api.graph.cascade.remove_book` / `api.graph.projection.reset_project`
   rather than calling them for real, per BRANCH.md §4/§9 (be2 has exclusive
   write access to the single shared Neo4j instance during a sprint; be1
   never touches it). The wiring is correct and exercised (the mocks assert
   the right ids are passed), but nobody has yet deleted a book against the
   *live* shared Neo4j and confirmed zero nodes/edges survive. Worth one pass
   during the merge train's integration run.

**A pre-existing conflict this story surfaced and fixed in the same commit:**
`api/pipeline/repository.py::create_book`'s idempotent-reingest fallback
(`get_book_by_hash`) looked up an existing book by content hash **globally**,
with no project scoping at all — a demo session uploading a file whose hash
happened to match *any* existing book anywhere (another private session's, or
the public corpus) was silently handed back that book's id and never got its
own book in its own project. This predates S9.8 (it's the same code path
`F1.5`'s idempotent re-ingest has used since Sprint 1) but is exactly the kind
of pooling ETH-2 exists to rule out, so it's fixed here rather than filed as a
gap: the fallback is now `get_book_by_hash_in_project`, and a genuine
cross-project collision surfaces as `IntegrityError` → `409`, not a reuse.

## be1 — S9.9 OCR path (§3.2) — formally deferred

**Decision: deferred, not built.** Checked what exists: `DocumentChunker`
takes an `ocr: bool = False` flag straight through to Docling's
`DocumentConverter(do_ocr=ocr)` (`api/pipeline/chunking.py`) — that is the
entire footprint. No text-density check, no automatic routing between the
digital and OCR paths, no scanned-PDF fixture, no page-provenance-survives-OCR
verification, no quality measurement. This has been the state since Sprint 2
(see `.agents/skills/codebase-memory/ingestion-pipeline.md`'s existing OCR
gotcha) and Sprint 8's retro (`plans/sprint-8/RETRO.md`) does not list OCR
among what it left room for — its carried-over items are a frontier judge key,
an extraction-mode switch, and ablation metric wiring, none of which touch
this.

**Why not built this sprint:** two structural blockers, not just time:

1. **RapidOCR's weights are not in the offline model cache.** The existing
   map already documents that RapidOCR downloads from `modelscope.cn` outside
   the HF cache the moment `ocr=True` is exercised — `make warm-models` never
   pre-warmed it, so a real OCR test run would violate the
   `MODELS_OFFLINE=1` / no-network testing contract (AGENTS.md) the whole
   suite depends on. Building the routing logic without ever being able to
   run it against real OCR output would be exactly the kind of code that
   "looks complete and is not" the sprint brief warned about for S9.8's
   deletion path — the same standard applies here.
2. **No scanned-PDF fixture exists**, and the corpus is digitally-typeset
   novels by design (public-domain, already-digital sources) — building one
   deliberately-scanned fixture plus a measured quality delta (what the
   conditional build asked for) is its own scoped piece of work, not a
   same-sprint add-on to S9.8's substantially larger privacy/deletion story.

**What this means for S9.9's own DoD line** ("OCR either working with
measured quality, or formally deferred in writing"): deferred in writing,
here and in `plans/BACKLOG.md`'s deferred-items table (updated in this
commit — see the row's new "Revisit" note).

**To actually build this in a future sprint:** (a) pre-warm RapidOCR's
weights into the shared model cache alongside Docling/BGE-M3 (do1's
`make warm-models`), (b) add one deliberately-scanned fixture PDF, (c) add a
text-density check in `DocumentChunker.load_document` (e.g. extracted
chars-per-page below a threshold) that re-converts with `ocr=True`, (d)
verify `chunk.meta.doc_items[*].prov[*].page_no` still resolves through
Docling's OCR backend the same way it does today for the digital text layer —
this is the one part of the whole feature that is genuinely risky, since the
existing map already flags provenance as "the whole product promise."

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

# Sprint 9 — fe1 HANDOFF

For be2 (S9.6 routing policy engine, S9.7 frontier API path) and do1 (cost
accounting) picking this up after fe1's stories land.

## S9.10 — Ops dashboard: exact swap points

The dashboard (`web/src/routes/ops/dashboard/`) is built against the frozen
contract shapes and already wired to every **live** route that exists today.
Two seams remain fixture-backed, both documented in code comments at the
point they're used, not just here:

1. **`GET`/`PUT /ops/routing-policy`** (`api/routes/ops.py`, currently
   `not_implemented(OWNER, "S9.6")`). `routing-control-panel.tsx` and
   `web/src/lib/inference-mode.ts`'s `useEffectivePolicy()` already call the
   real hooks (`useRoutingPolicy`/`useSetRoutingPolicy`, generated from the
   frozen `RoutingPolicyOut` contract) — the moment the handlers return real
   data instead of 501, **no frontend change is needed**. The panel already
   syncs its local edit state from a live response (`routing-control-
   panel.tsx`'s `syncedVersion` render-time check) and already calls the real
   `PUT` on "Apply to live traffic," reporting success or "preview only" off
   whatever the response actually is.

2. **`CostBreakdown`** (`api/contracts/api.py`) has no route at all yet. The
   routing panel's cost-per-query number and the 7-day trend chart
   (`fixtures.ts`'s `PURPOSE_UNIT_COST_USD`/`COST_TREND`) are a labelled
   placeholder unit-cost table, not a live meter. When a route exists (the
   natural shape: `GET /ops/cost-breakdown?window=` returning one
   `CostBreakdown`, or a list of them for the trend), swap:
   - `fixtures.ts`'s `costPerQueryFor` → a real per-purpose cost read off the
     latest `CostBreakdown.by_purpose`.
   - `fixtures.ts`'s `COST_TREND` → a `useQuery` over a windowed listing.
   - Delete `routes/ops/dashboard/types.ts`'s hand-mirrored `CostBreakdown`
     type once `pnpm gen:api` can generate `Schemas["CostBreakdown"]` (it
     can't today — FastAPI only emits a schema for a type a route
     references).

3. **Accuracy delta** already prefers a real `GET /ops/eval-runs/latest`
   result (built since S8.8) and only falls back to
   `fixtures.ts`'s `FALLBACK_MODEL_AXIS_RESULTS` on a 404 (no run recorded in
   this database yet). Nothing to swap here — just run `make eval-ablation`
   against a worktree's own database and the panel picks up real numbers on
   its own.

`web/src/lib/api/schema.d.ts` was regenerated against the shared integration
API mid-sprint (`API_URL=http://localhost:8000 pnpm gen:api`) — it now
includes `EvalRunOut`/`EvalResultOut`/`AblationConfig`/`MetricSet`/
`ReviewAlertsOut`/`QueryLatencyOut` as real generated types for the first
time. `routes/ops/evals/types.ts` (Sprint 8) still hand-mirrors its own copy
of the first four — that refactor was left for whoever next touches that
screen, per its own file-header note; the ops dashboard's new code (S9.10)
uses the generated ones directly and does not depend on `evals/types.ts`.

## S9.11 — SCR-1 (see `plans/sprint-9/SCR.md`)

`DoneEvent`/`RouteEvent` carry no field for which inference mode actually
served a given past answer — only the currently configured policy is
knowable client-side (`lib/inference-mode.ts`'s `useEffectivePolicy`). Not
blocking this sprint's DoD, but real: once S9.7's routed/fallback behavior
exists, "the policy says local" and "this particular answer happened to fall
back to frontier" can diverge, and today's UI can't tell the difference.
Proposed field and exact call sites to update are in the SCR.

## Testing

`jest-axe` + `axe-core` added as devDependencies (`web/package.json`,
`pnpm-lock.yaml` — installed and verified against
`pnpm install --frozen-lockfile`, which is what `docker-compose.yml`'s
`test-web` service runs). `web/tests/axe.ts` is the shared `runAxe` helper +
the Vitest `Assertion` type augmentation (jest-axe ships no Vitest-native
matcher). No CI config changes were needed or made — `test-web` already runs
`pnpm run test` (`vitest run`), which picks up every `.test.tsx` file
automatically, axe-based or not.

## Everything else

S9.10-13 are otherwise self-contained inside `web/src/**` — no other agent's
files were touched, and no other SCR/DCR was needed beyond SCR-1 above.

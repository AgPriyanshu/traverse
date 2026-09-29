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

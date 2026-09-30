# Traverse — Architecture

This is the "start here" document. It explains what Traverse does, how the pieces
fit together, how to run it, and the rules that keep it correct. It is meant to be
read top to bottom once, then used as a map.

For depth on one subsystem, the per-topic maps in
[`.agents/skills/codebase-memory/`](.agents/skills/codebase-memory/SKILL.md) go
further. For product intent see [`traverse-prd.md`](traverse-prd.md); for the
reasoning behind the extraction design see
[`docs/writeup-two-pass-extraction.md`](docs/writeup-two-pass-extraction.md).

## Contents

1. [What Traverse is](#1-what-traverse-is)
2. [The big picture](#2-the-big-picture)
3. [Repository map](#3-repository-map)
4. [Running it](#4-running-it)
5. [Data stores and the source of truth](#5-data-stores-and-the-source-of-truth)
6. [The ingestion pipeline](#6-the-ingestion-pipeline)
7. [Characters, identity and the graph](#7-characters-identity-and-the-graph)
8. [Answering a question](#8-answering-a-question)
9. [Spoiler safety](#9-spoiler-safety)
10. [The human review queue](#10-the-human-review-queue)
11. [The LLM runtime](#11-the-llm-runtime)
12. [Privacy, sessions and quotas](#12-privacy-sessions-and-quotas)
13. [The web app](#13-the-web-app)
14. [Operations, evaluation and observability](#14-operations-evaluation-and-observability)
15. [Rules that keep it correct](#15-rules-that-keep-it-correct)
16. [Working in this repository](#16-working-in-this-repository)
17. [Pitfalls we have already hit](#17-pitfalls-we-have-already-hit)

---

## 1. What Traverse is

Upload a novel as a PDF. Traverse reads it, builds a **graph of every named
character and every evidenced relationship between them**, and answers
plain-English questions with a streamed answer whose every claim links to the
**exact page** that supports it.

Three ideas define the design, and most decisions below follow from them:

- **Page-exact citation is the product.** Every chunk of text carries a page
  range. Every relationship edge carries at least one evidence row with a quote
  and a page. A claim that cannot be cited is dropped, not softened.
- **Nothing is invented.** Relationships must name characters already on the
  roster, quote text that really appears in the cited chunk, and use a predicate
  from a closed vocabulary. Five of the six answer types are assembled straight
  from stored rows — the model never free-writes them.
- **A reader's position is respected.** Asking "who is X?" halfway through a book
  must not reveal what happens in chapter 40. Spoiler scope is enforced in the
  data layer, not in the UI.

A worked example that motivates the whole pipeline: *Wuthering Heights* has two
characters called Catherine. A system that merges them has failed at the one
thing it exists to do, so the pipeline pauses and asks a human rather than
guessing.

## 2. The big picture

```
                              ┌────────────────────────────┐
   Browser  ── same origin ─▶ │ web (nginx + React SPA)    │
                              └──────────────┬─────────────┘
                                             │ /api/*
                              ┌──────────────▼─────────────┐
                              │ api  (FastAPI)             │  reads, SSE answers,
                              │  routes → repositories     │  review + ops endpoints
                              └───┬────────┬────────┬──────┘
                 enqueue stages   │        │        │  Cypher (templated)
                                  ▼        ▼        ▼
                        ┌─────────────┐ ┌────────┐ ┌────────┐
                        │  RabbitMQ   │ │Postgres│ │ Neo4j  │
                        └──────┬──────┘ │+pgvector│ │ graph  │
                               │        └───▲────┘ └───▲────┘
                        ┌──────▼──────┐     │          │ projected from Postgres
                        │celery-worker│─────┴──────────┘
                        │ 9 stages    │──▶ MinIO (PDFs, page renders)
                        └──────┬──────┘
                               │ every model call, by purpose
                        ┌──────▼──────┐        ┌──────────────────┐
                        │ api/llm     │──────▶ │ vLLM (Qwen3-8B)  │  local
                        │ routing     │──────▶ │ frontier API     │  optional
                        └─────────────┘        └──────────────────┘
                                         Langfuse (optional) traces every call
```

**Postgres is the source of truth. Neo4j is a rebuildable projection** used for
graph traversal. If they ever disagree, Postgres wins and `make graph-rebuild`
re-projects.

## 3. Repository map

```
api/                 Backend (Python 3.11+, containers run 3.12; FastAPI, Celery, SQLModel, LangGraph)
  main.py            App factory; mounts routers under /api; lifespan connects Neo4j
  routes/            Thin HTTP layer: books, characters, graph, query, review, ops
  contracts/         Pydantic response/request models + enums. The API contract.
  db/                Engine, SQLModel tables (models/), Alembic migrations
  config/settings.py Every setting, read from environment
  pipeline/          Parse → chunk → chapters → embed; page render; upload privacy
  extraction/        Pass 1: roster discovery, alias cascade, collision guard, tiering
  reconcile/         Merging one book's characters into a project-wide roster
  relations/         Pass 2: relationship extraction, verification, aggregation
  graph/             Neo4j client, ontology, projection, graph queries, checkpointer
  retrieval/         Dense + lexical + fused (RRF) search over chunks
  query/             Router, templates, generation, grounding, citations, SSE pipeline
  review/            Human review queue: payloads, priority, resolution, workflow gates
  llm/               The only place a model is called: routing, structured output, budget
  eval/              Ablation config switching, confidence calibration
  ops/               Telemetry, health, budget guard, upload guard, eval read APIs
  workers/           Celery app, retry policy, stage recording
  tasks.py           The frozen ingestion chain (stage names + ordering)
  tests/             Backend tests, against a real Postgres
web/                 Frontend (React 19, TypeScript, Chakra UI, TanStack Query)
  src/routes/        One folder per screen
  src/lib/api/       Typed client generated from the API's OpenAPI document
  src/design-system/ Theme and tokens
  tests/             Vitest + Testing Library (+ axe accessibility checks)
eval/                Gold data (per novel) and metric code
  gold/              Hand-labelled rosters, relations and questions
scripts/             Operator tools: seeding, ingesting, ablation, chaos test, gates
corpus/              Public-domain demo novels and their manifest
docker/              Postgres init, nginx (TLS edge) config
docs/                Long-form writeups
plans/               Sprint plans, retros, hand-offs, the project retro
.agents/             Agent-facing context: skills (codebase maps) and rules
```

Reading order for a newcomer: `api/tasks.py` (the pipeline's shape) →
`api/contracts/api.py` (what the API promises) → `api/query/pipeline.py` (a whole
request) → `web/src/routes/routes.tsx` (the screens).

## 4. Running it

### Prerequisites

- Docker with Compose v2. That is all you need to run and test everything —
  nothing is installed on the host.
- For real extraction speed: an NVIDIA GPU (vLLM serves Qwen3-8B). Without one
  the stack still runs, but model calls are slow or must go to a frontier API.

### First run

```bash
make env          # creates .env from .env.example (and generates Langfuse secrets)
make up           # Postgres, Neo4j, RabbitMQ, MinIO, migrations, api, worker, web — no GPU
make up-gpu       # adds vLLM and sets INFERENCE_MODE=local
make health       # /health with per-dependency status
make seed         # fetch and paginate the public-domain demo corpus
make ingest BOOK=pride_and_prejudice
```

Then open the web app (default `http://localhost:5174`) and the API docs
(`http://localhost:8000/docs`).

### Compose files and profiles

| File / profile | Purpose |
| --- | --- |
| `docker-compose.yml` | The base stack. |
| `docker-compose.dev.yml` (`make up-dev`) | Hot-reload API, Vite dev server, Flower. |
| `docker-compose.gpu.yml` (`make up-gpu`) | vLLM with the local model. |
| profile `obs` (`make up-obs`) | Langfuse tracing. |
| `docker-compose.ci.yml` | Minimal subset used in CI. |
| `docker-compose.prod.yml` (`make up-prod`) | CPU profile behind an nginx TLS edge — verified locally only. |
| profile `test` | The `test` and `test-web` runners. |

### Ports (all overridable in `.env`)

| Service | Port |
| --- | --- |
| web | 5174 (dev server: 5173) |
| api | 8000 |
| Postgres | 5433 |
| Neo4j | 7474 (browser), 7687 (bolt) |
| RabbitMQ | 5672, 15672 (management) |
| MinIO | 9002 (API), 9003 (console) |
| vLLM | 8080 |
| Langfuse | 3000 |

### Everyday commands

```bash
make test          # backend + frontend, in the containers that match CI
make test-api      # backend only
make test-web      # frontend lint, typecheck, tests
make lint / make fmt
make logs S=api    # tail one service
make shell-db      # psql          make shell-neo4j   # cypher-shell
make openapi       # dump the live OpenAPI document; then `pnpm --dir web exec openapi-typescript`
                   # regenerates web/src/lib/api/schema.d.ts from it
make migrate       # alembic upgrade head
make graph-rebuild BOOK=<key>   # wipe + re-project a book's graph from Postgres
```

`make help` lists every target with a description.

### Running tests correctly

Always go through the containers (`make test-api`, or `docker compose --profile
test run --rm test …`). The image is **built from source, not bind-mounted**, so
after editing code run `docker compose --profile test build test` first or you
will test stale code. If you invoke `pytest` directly inside the container, pass
explicit paths (`api/tests eval/tests …`) — a bare `pytest` from the wrong
directory silently drops the project's async-mode configuration and reports
hundreds of false failures.

### Configuration

Every setting lives in `api/config/settings.py` and has a key in `.env.example`.
The ones you will touch most:

| Setting | Meaning |
| --- | --- |
| `INFERENCE_MODE` | `local`, `api` or `routed` — where model calls go. |
| `VLLM_BASE_URL`, `LLM_MODEL` | The local model endpoint. |
| `FRONTIER_MODEL`, `FRONTIER_API_KEY` | Optional frontier model. Blank by default: no data leaves the machine. |
| `LLM_MAX_CONCURRENCY` | Shared ceiling on in-flight model calls (default 8). |
| `EMBEDDING_DEVICE` | `cpu` or `cuda` for BGE-M3. |
| `MODELS_OFFLINE` | Forbid model downloads (tests run offline). |

Secrets are never committed. `.env` is git-ignored.

## 5. Data stores and the source of truth

| Store | Holds | Role |
| --- | --- | --- |
| **Postgres + pgvector** | Everything durable | Source of truth |
| **Neo4j** | Characters and relations as a graph | Rebuildable projection for traversal |
| **MinIO** (S3) | Uploaded PDFs, rendered page images and span JSON | Object store |
| **RabbitMQ** | Celery task messages | Work queue |
| **LangGraph checkpoint tables** (in Postgres) | Paused review workflows | Durable pause/resume |

The main tables, grouped by purpose (full column lists: `data-model.md`):

- **Structure of a book:** `project` (one novel or a series), `book` (belongs to a
  project, has a `series_order` and a unique `content_hash`), `chapter`,
  `documentchunk` (text, `pages[]`, `page_start/end`, a 1024-dim embedding, a
  full-text `tsv`), `scene`, `dialogue_line`.
- **Who is in it:** `character` (project-scoped, unique per canonical name),
  `character_appearance` (per book), `character_mention` (every occurrence, with
  page and resolution method), `book_character_candidate` and
  `rejected_candidate` (pass-1 staging).
- **How they relate:** `relation` (subject, predicate, object, family, status,
  hearsay flag, validity span in series position) and `relation_evidence` (the
  quote and page that prove it).
- **Pipeline bookkeeping:** `ingestion_run`, `ingestion_stage` (timings, tokens,
  cost, errors per stage per attempt).
- **Human oversight:** `review_task`, `correction_feedback`.
- **Answering:** `conversation`, `conversation_turn`, `query_log`.
- **Operations:** `eval_run`, `eval_result`, `calibration_model`,
  `routing_policy`, `cost_snapshot`, `upload_session`.

Enums are stored as **native Postgres enum types**, so adding a value needs an
`ALTER TYPE … ADD VALUE` in a migration.

Constraints that carry meaning:

| Constraint | Why |
| --- | --- |
| `book.content_hash` unique | Re-uploading the same file is idempotent. |
| Chunk page range `NOT NULL` | Page provenance is mandatory, enforced by the database. |
| `character (project_id, canonical_name)` unique | One "Harry Potter" per project, not seven. A single book is a one-book project — there is no second code path. |
| `relation_evidence` cascades from `relation` | Evidence cannot outlive its edge. |
| Embeddings normalised, cosine index | Distances are only valid on unit vectors. |

### Migrations

Alembic, in `api/db/migrations/versions/`. **One migration per sprint, written by
the orchestrator at the contract freeze**; contributors file a change request
instead of writing one, because two branches both creating the next revision
produces a history Alembic refuses to run. LangGraph's checkpoint tables are
created by `api/graph/checkpoint.py` and are deliberately excluded from
autogenerate.

## 6. The ingestion pipeline

Uploading a PDF (`POST /api/projects/{id}/books`) streams it to MinIO while
hashing it, creates the `book`, and enqueues a **Celery chain of nine stages**,
declared once in `api/tasks.py`:

| # | Stage (frozen task name) | What it does |
| --- | --- | --- |
| 1 | `pipeline.parse_and_chunk` | Docling parses the PDF; the chunker builds chunks that each keep the pages they came from. |
| 2 | `pipeline.segment_chapters` | Finds chapters by regex, with an LLM fallback (temperature 0) for ambiguous headings. |
| 3 | `pipeline.embed_chunks` | BGE-M3 embeddings, normalised. Resumable: only rows still missing an embedding. |
| 4 | `pipeline.extract_characters` | **Pass 1** — discover candidate names and mentions; reject non-characters. |
| 5 | `pipeline.resolve_aliases` | Collapse aliases ("Lizzy", "Miss Bennet") into identities; guard name collisions. |
| 6 | `pipeline.reconcile_characters` | Merge this book's characters into the project-wide roster (matters for series). |
| 7 | `relations.extract` | **Pass 2** — extract relationships against the fixed roster. |
| 8 | `relations.aggregate` | Merge repeated assertions into one edge with all its evidence; close superseded edges. |
| 9 | `graph.upsert` | Project the result into Neo4j. |

Stage names are the contract: each package registers its tasks under the frozen
name, so the chain never imports implementations. `ingestion_chain(book_id,
from_stage=…)` can restart from the middle — the review queue uses this to resume
after a human decision.

**Every stage runs inside `workers/stages.py::stage()`**, which records a row in
`ingestion_stage` (state, attempt, duration, tokens, cost, error) and keeps the
`book.status` column in step. This is what `GET /api/books/{id}/status` and the
ops dashboard read.

### Failure handling

Errors are classified up front: **`TransientError`** is retried by Celery,
**`PermanentError`** is not (retrying a malformed PDF four times wastes twenty
minutes). Docling has a known cold-start flake where a page occasionally fails
then succeeds on retry; that surfaces as a transient `PageParseError`. Stages that
call the LLM handle a cut-off or oversized reply by **splitting the input in half
and retrying**, recursively, rather than failing.

### Page provenance

Pages come from Docling's item `prov` metadata. An empty page list is treated as a
bug to raise, never defaulted to `0`. Page images are rendered on demand straight
from the source PDF with `pypdfium2` (not through Docling), cached in MinIO along
with text-span boxes for highlighting.

## 7. Characters, identity and the graph

### Why two passes

One pass — "read a chunk, emit relationships" — invents people and mismatches
names. Traverse separates the problems:

1. **Pass 1 (roster).** Find who exists: candidate names with contexts, then
   rejection of non-persons, alias resolution, collision detection, tiering
   (protagonist / major / minor / mentioned).
2. **Pass 2 (relations).** With the roster fixed, extract relationships between
   *known* characters only. The roster is placed at the start of the prompt and is
   **byte-identical across calls**, so vLLM's prefix cache reuses it — changing
   its order or formatting silently destroys that saving.

The full argument, with numbers, is in `docs/writeup-two-pass-extraction.md`.

### Alias resolution

A cascade, cheapest first: exact → normalised (case, punctuation) → honorific
(`honorifics.yaml`) → nickname (`nicknames.yaml`) → embedding similarity → LLM
adjudication → human. Each mention records the method that resolved it. A
**collision guard** stops two distinct people sharing a surname from being merged
(the two Catherines) and raises a review task instead.

### Series

A project can hold several books in order. Character identity is project-wide, so
`reconcile_characters` matches each new book's characters to the existing roster,
using blocking, matching, and signals like death (a dead character cannot appear
alive later). Derived fields (first appearance, mention counts, tier) are
**recomputed from all appearances**, never accumulated, so ingesting books out of
order self-corrects.

### The ontology

Relationship types are **data, not code**: `api/graph/ontology.yaml` declares
families (`kinship`, `romantic`, `social`, `adversarial`, `structural`) and their
predicates with inverses and symmetry. Adding a predicate there makes it valid in
the enum, the API and the extraction prompt with no Python change — which is what
keeps the prompt and the validator from drifting apart. It also declares legal
*transitions* (acquaintance → married), which drive temporal handling.

### Evidence rules for edges

An edge cannot be written without at least one evidence row (`graph.upsert`
refuses). A quote must be locatable in its cited chunk (`pipeline/quotes.py`:
exact, then whitespace-normalised, then fuzzy). Subject and object must be on the
roster. A relationship that changes over time **closes the old edge and opens a
new one** — the history is the interesting part, so it is never overwritten.
Hearsay edges keep their speaker ("According to Mrs Bennet…").

Validity is measured in **series position** `(book_order, chapter)` and compared
as a row in SQL. A standalone book is simply `(1, chapter)`.

## 8. Answering a question

`POST /api/query` streams **Server-Sent Events**. The pipeline
(`api/query/pipeline.py::answer_question`) does:

1. **Route.** One structured LLM call classifies the question *and* extracts the
   entity phrases (a second pass would double latency). Classes:
   `character_lookup`, `relationship_lookup`, `path`, `aggregation`,
   `series_arc`, `narrative`, `ambiguous`.
2. **Resolve names** to character ids with `extraction/resolution.py` — a
   deterministic cascade (name, nickname, partial, fuzzy, relative like "her
   sister"), **never an LLM call**, under 50 ms. Names the reader has not reached
   yet are filtered out first.
3. **Gather evidence** by class:
   - *character lookup* → the character record, aliases, first appearance,
     strongest visible relationships and top mention passages;
   - *relationship / aggregation* → **templated Cypher** (a fixed library of
     parameterised statements; free-form Cypher never reaches the database),
     hydrated through Postgres;
   - *path* → shortest path with each hop cited;
   - *series arc* → how a pair's relationship changed across books;
   - *narrative* → graph-scoped hybrid retrieval then generation.
4. **Ground.** The five graph-derived classes are assembled directly from stored
   rows, so they are grounded by construction. Only *narrative* free-generates,
   and its output is checked; unsupported sentences are **removed** and the
   answer says what it could not establish. "Not established in this novel" is a
   correct answer.
5. **Cite.** Each claim carries book, chapter and page, resolving to the rendered
   page with the span highlighted. Quotes are capped at 400 characters.
6. **Stream** `route`, `token`, `citation`, `interrupt` (a clarifying question),
   `done` and `error` events, and write a `query_log` row with per-stage latency.

**Retrieval is graph-first:** resolve names → pull the characters' own evidence →
hybrid search *within that constrained set* → whole-book search only as a last
resort, logging which tier answered. Hybrid search fuses dense (pgvector cosine)
and lexical (`ts_rank_cd`) results with **reciprocal rank fusion (k = 60)**,
because the two scores are not comparable and normalising them is where hybrid
search usually goes wrong.

**Conversations** keep context across turns (a token budget, not a turn count; an
older turn is summarised from its own resolved names without another model call).

## 9. Spoiler safety

Spoiler scope is a **required parameter, not an optional filter.**

- The reader's position is a `ReadingScope(book_order, chapter)`
  (`api/query/scope.py`). Every graph, retrieval and generation function takes one
  with no default — omitting it is a `TypeError`, not a silent "show everything".
  `ReadingScope.unlimited()` exists for the few callers that legitimately want no
  limit (the review queue) and makes that an explicit, greppable choice.
- Over HTTP, `limit_book_order` is **required** on every scoped endpoint;
  `limit_chapter` is optional.
- **`chapter = null` means "no chapter cap within that book"** — everything in
  the book is visible. It does *not* mean "only things with no chapter". "Caught
  up" is expressed by the web app as the last book's order with no chapter cap,
  never by omitting `limit_book_order`.
- Filtering is applied in every layer that can leak: entity visibility, edge
  visibility, each evidence row's page (a visible edge must not cite a *later*
  reassertion of itself), Neo4j's denormalised `page_refs`, retrieval, and the
  aggregation answer's own sentences. `api/tests/query/test_spoiler_leakage.py`
  measures leakage across every read surface.

## 10. The human review queue

The pipeline **stops when it is unsure** instead of guessing, and a human answers
in seconds.

- **Task types:** `merge_characters`, `merge_across_books`, `confirm_relation`,
  `resolve_conflict`, `classify_candidate`, `confirm_chapter_split`. The API
  returns them as a discriminated union on `task_type`
  (`ReviewTaskPayload`), so a renderer never reads an untyped dict.
- **Real pauses.** `api/review/workflow.py` uses LangGraph `interrupt()` on the
  Postgres checkpointer, with two gates per book: `roster` (unresolved character
  merges block relationship extraction, because edges must not be keyed against a
  roster that might still change) and `conflict`. A blocked stage defers quietly.
  Killing the worker mid-review loses nothing; resolving a task resumes the run
  from the right stage.
- **Priority is blast radius**, recomputed on every read: a merge on a protagonist
  outranks a confirmation on a minor pair.
- **Resolution** (`review/resolution.py`) is idempotent, writes
  `correction_feedback` (what the model believed at decision time, and what the
  human chose — the raw material for confidence calibration), and resumes the
  paused gate.
- **`human_verified` is sacred.** A verified character, relation or chapter is
  never overwritten by a re-run, enforced in the repository layer. If a re-run
  disagrees with a verified value, it raises a *new* review task (deduplicated)
  instead of overwriting.

The queue UI is keyboard-first (`j`/`k` to move, one key per decision) with bulk
accept for high-confidence groups.

## 11. The LLM runtime

**`api/llm` is the only place a model is called.** A call that bypasses it is
invisible to the cost dashboard and the routing policy.

- **Routing is by purpose, not call site:** `chapter_classify`,
  `character_extract`, `relation_extract`, `adjudicate`, `answer`, `judge`.
  `route_for(purpose)` decides the model, so switching models is a config change.
- **Live policy.** `GET/PUT /api/ops/routing-policy` reads and writes an
  append-only `routing_policy` table; a `PUT` changes the very next call in the
  same process, no restart. Each `query_log` row records the policy version.
- **Local first.** Default is a self-hosted `Qwen/Qwen3-8B-AWQ` behind vLLM
  (thinking mode off — it multiplied token cost ~60× for no gain here). A
  frontier model is optional (`FRONTIER_MODEL` + key). If it is unconfigured, or a
  frontier call fails transiently, `adjudicate`/`answer`/`judge` fall back to
  local. The `judge` purpose should be frontier — a model grading its own output
  is not a measurement — and it refuses outright without one.
- **Residency.** `INFERENCE_MODE=local` is a floor that applies to *every*
  purpose; the UI labels wherever a query can leave the machine.
- **`structured_call`** is how everything gets typed output: a Pydantic schema, one
  retry with the validation error appended, both attempts traced. Errors are
  classified transient vs permanent, and "input too large" becomes
  `LengthLimitError` so callers split their input.
- **Bounded concurrency.** A shared semaphore (default 8) sits below vLLM's own
  limit. It is rebuilt when the event loop changes, because each Celery task runs
  in a fresh loop and a semaphore bound to a dead loop deadlocks.
- **Budget.** `plan_batches` sizes prompts with the model's real tokenizer and
  reserves room for the reply (at least `llm_max_output_tokens`, since vLLM
  rejects input plus `max_tokens` over the context).
- **Timeouts.** Requests carry a deadline (300 s local, 120 s frontier).
- **Tracing.** Every call is tagged with `purpose` and `book_id` in Langfuse; the
  cost dashboard reads those tags.

## 12. Privacy, sessions and quotas

Uploads are private by construction (`api/pipeline/session_privacy.py`).

- `POST /api/projects` mints an **upload session** and returns its token in the
  `X-Session-Token` response header; the web client stores it and sends it on every
  request. The project is linked 1:1 to that session.
- A project with **no** live session is public (the seeded public-domain corpus).
  A missing or wrong token on a private project is **404, never 403** — a private
  project must be indistinguishable from a nonexistent one.
- `content_hash` is unique install-wide but reuse is project-scoped: an identical
  file uploaded under a *different* project is a 409, never silently shared.
- **Quota and abuse guards** (`api/ops/upload_guard.py`, wired into the upload
  route): per-session book count, per-IP daily limit, page limit, and a
  public-domain heuristic (copyright markers). They return 429 / 413 / 422.
- **Deletion is real:** `DELETE /api/books/{id}` removes Postgres rows, MinIO
  objects, Langfuse traces and the Neo4j projection, and removes an emptied
  project and its session. A 24-hour TTL sweep does the same for expired sessions
  (`make upload-sweep`).

## 13. The web app

React 19 + TypeScript + Chakra UI v3, routing with React Router, server state with
TanStack Query, the graph drawn with Cytoscape (fcose layout).

- **Same-origin.** nginx serves the SPA and proxies `/api`, so there is no CORS.
- **Typed client.** `web/src/lib/api/schema.d.ts` is generated from the API's
  OpenAPI document (`make openapi`, then `openapi-typescript`); `hooks.ts` wraps each endpoint in a query
  hook and `query-keys.ts` centralises cache keys. A backend contract change
  shows up as a TypeScript error.
- **Screens** (`web/src/routes/routes.tsx`): books library and upload; a book with
  overview, chapters, page viewer, characters, graph, ask and review tabs;
  project-level characters, graph and ask; the ops dashboard and eval results;
  and a public landing page.
- **Reading position** is one persistent slider per project
  (`lib/reading-position.ts`), stored in `localStorage` and turned into
  `limit_book_order` / `limit_chapter` on every scoped call.
- **Session token** is captured from `POST /projects` and replayed by the client
  and the uploader (`lib/api/session-token.ts`).
- **Answers stream** over SSE and render inline citations that link to the page
  viewer, preserving the conversation when you click through and come back.
- **Accessibility** is tested (axe) on the main screens; the layout works down to
  400 px.

## 14. Operations, evaluation and observability

- **Ops dashboard** (`/ops`): cost by stage and purpose, latency percentiles and
  throughput, queue depth, pipeline health (failure rates, dead letters, trace
  links) and the routing-policy control that shows cost and accuracy moving
  together. Backed by `api/ops/*` and `GET /api/ops/*`.
- **Health.** `GET /health` reports each dependency (db, broker, neo4j, object
  store, llm).
- **Budget guard.** A monthly spend cap can pause the worker (`make budget-check`).
- **Evaluation** lives in `eval/`: hand-labelled gold data for two novels (roster,
  relations, 63 questions across six classes), metric code, and runners
  (`make eval-relations`, `eval-answers`, `eval-reconciliation`).
- **Ablation** (`make eval-ablation`): runs one axis at a time — extraction,
  retrieval mode, model — against the recommended setting of the others, cached
  and resumable, storing `eval_run` / `eval_result`. `api/eval/ablation.py`
  switches configurations; the README's results table is generated from the last
  run (`make eval-ablation-readme`).
- **Regression gate** (`make regression-gate`): fails if a headline metric drops
  more than two points against the stored baseline.
- **Calibration** (`api/eval/calibration.py`): fits a reliability curve from
  `correction_feedback` and reports expected calibration error.
- **Durability drill** (`make chaos-test`): kills the worker, database and API
  mid-work and checks nothing is lost. Run it only on an integration host.

Some numbers depend on things a developer must supply — a frontier API key for
judge-scored accuracy, and real reviewer decisions for calibration. Where they are
absent the tooling reports "blocked", never a made-up figure.

## 15. Rules that keep it correct

These are enforced in code and must not be relaxed to make a test pass.

| Invariant | Where | Why |
| --- | --- | --- |
| Every chunk has a non-null page range | database constraint | Page-exact citation is the product. |
| No relation edge without ≥ 1 evidence item | `graph.upsert` | An unevidenced edge is a hallucination with a UI. |
| A quote must appear in its cited chunk | relation validator | Catches fabricated evidence. |
| Subject and object must be on the roster | relation validator | Off-roster names are invention. |
| Predicates come from the ontology | ontology loader | Closed vocabulary, prompt and validator cannot drift. |
| Human-verified values are never overwritten | repository layer | A correction that gets clobbered kills the review feature. |
| Temporal change closes the old edge, never overwrites | `relations.aggregate` | History is the point. |
| Scope is a required parameter | `ReadingScope` | Spoilers cannot be leaked by forgetting an argument. |
| A private project looks nonexistent to others | `session_privacy` | 404, never 403. |
| Neo4j holds no fact absent from Postgres | `graph.upsert` | It must stay rebuildable. |
| Free-form Cypher never reaches the database | `query/templates.py` | Only declared, parameterised statements run. |

## 16. Working in this repository

This project is built by several agents and people in parallel worktrees, so a few
conventions matter:

- **Read the conventions first:** [`AGENTS.md`](AGENTS.md) (shared),
  [`api/AGENTS.md`](api/AGENTS.md), [`web/AGENTS.md`](web/AGENTS.md).
  [`BRANCH.md`](BRANCH.md) defines ownership, branch names and the merge train.
- **Use the maps, not a broad search.** `.agents/skills/codebase-memory/` has one
  short map per subsystem. If a map is wrong, fix it in the same change as the code.
- **Frozen surfaces.** `api/contracts/`, `api/db/models/` and the design tokens are
  changed by the orchestrator at a sprint's contract freeze; everyone else files a
  change request.
- **Style highlights.** No comment or docstring at the top of a file; comment only
  what code and names cannot say; Google-style docstrings on public functions, none
  on classes; all I/O is async; database access goes through a repository module;
  no absolute host paths; no secrets in the repo.
- **Commits** are conventional (`feat(scope): … [S7.2]`), one per completed story.
- **Never work directly on `master`.** Branches start `ai/…` and integrate on
  `ai-master`; promoting to `master` is a human decision through a reviewed PR.

## 17. Pitfalls we have already hit

Learned the hard way; each has a regression test or a comment at the site.

- **`expire_on_commit` crashes.** After a commit, SQLAlchemy expires every loaded
  object. Reading an attribute afterwards tries to lazy-load outside an awaitable
  context and raises `MissingGreenlet`. Capture the values you need *before* the
  commit, `await session.refresh(obj)` first, or open the session with
  `expire_on_commit=False` when you legitimately hold objects across commits. The
  test session fixture sets it to `False`, which **hides** this bug — verify by
  calling the real endpoint.
- **`chapter = None` is "no cap", not "no chapter".** An inverted filter here made a
  finished book look almost empty.
- **Stale event loops.** Anything bound to one loop (the LLM semaphore, the Neo4j
  driver) must be rebuilt when the running loop differs, because each Celery task
  starts a fresh loop.
- **Delete-and-reinsert loses identity.** Re-running a stage used to regenerate
  primary keys and cascade-delete dependent rows. Upsert on the natural key instead.
- **The test image is not bind-mounted.** Rebuild it after editing code, and run
  `ruff format` with the source mounted or it edits an ephemeral copy.
- **Circular imports through `api.llm`.** `api.llm` → `workers.errors` → the
  `workers` package → `pipeline` → `api.llm`. Import `pipeline` lazily inside
  `workers/stages.py`.
- **Qwen3 thinking mode** multiplies completion tokens enormously; it is off.
- **Shared-host contention.** Several stacks sharing one Docker host will
  occasionally recreate each other's `db` or `neo4j` container mid-test. If a run
  produces hundreds of connection errors, check the containers before suspecting
  the code.

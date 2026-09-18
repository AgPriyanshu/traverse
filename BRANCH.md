# BRANCH.md — parallel agent workflow

How four Claude agents build Traverse concurrently without stepping on each other.
Read this before creating a worktree. Every rule here exists because breaking it
costs a merge conflict that a subagent cannot resolve without human help.

---

## 1. The core constraint

Four agents editing one Python package will collide on exactly three things:

1. **SQLModel model files** — everyone wants to add a table.
2. **Alembic migrations** — linear `down_revision` history; two agents writing
   migration `0006` produces a branch Alembic refuses to run.
3. **Shared wiring** — `routes/__init__.py`, `tasks.py`, `settings.py`,
   `docker-compose.yml`.

The workflow therefore splits into two modes:

| Mode | Who | When | What |
|---|---|---|---|
| **Contract freeze** | Orchestrator only, on `ai-master` | Day 1 of every sprint | Models, the sprint's single migration, Pydantic contracts, route stubs, task-name registry, settings keys |
| **Parallel build** | 4 agents, in worktrees | Days 2–4 | Implementation only, inside owned directories |

**No agent ever writes a migration or edits a shared file.** If an agent needs a
schema change mid-sprint it files a Schema Change Request (§8) and the
orchestrator lands it on `ai-master`; everyone rebases.

---

## 2. Agent roster and ownership

Ownership is by **directory**, and it is exclusive. If a path is not in your
owned list, you do not create, edit, or delete it — you raise a request.

### Backend Engineer 1 — `be1`
*Ingestion and character extraction. Everything from a PDF to a resolved roster.*

```
OWNS      api/pipeline/**          parse, chunk, embed, chapter segmentation
          api/extraction/**        pass-1 discovery, alias clustering, tiering
          api/workers/**           Celery worker bootstrap, warmup, registry
          api/routes/books.py      upload, status, page render endpoints
          api/tests/pipeline/**
          api/tests/extraction/**
FORBIDDEN api/graph/**  api/query/**  web/**  docker-compose.yml
          api/db/models/**  api/db/migrations/**  api/contracts/**
```

### Backend Engineer 2 — `be2`
*Relationships, the graph store, and the query layer. Roster in, cited answer out.*

```
OWNS      api/graph/**             ontology config, Neo4j client, upsert, traversal
          api/relations/**         pass-2 extraction, aggregation, conflict resolution
          api/query/**             router, Cypher templates, hydration, grounding
          api/routes/characters.py api/routes/graph.py api/routes/query.py
          api/routes/review.py
          api/tests/graph/**  api/tests/relations/**  api/tests/query/**
FORBIDDEN api/pipeline/**  api/extraction/**  web/**  docker-compose.yml
          api/db/models/**  api/db/migrations/**  api/contracts/**
```

### Frontend Engineer 1 — `fe1`
*The entire web application.*

```
OWNS      web/src/**  web/index.html  web/package.json  web/vite.config.ts
          web/tsconfig*.json  web/.oxlintrc.json  web/tests/**
FORBIDDEN api/**  docker-compose.yml  web/Dockerfile  web/nginx.conf
```

### DevOps Engineer 1 — `do1`
*Everything that runs, deploys, seeds, or measures the system.*

```
OWNS      docker-compose.yml  docker-compose.*.yml  docker/**
          api/Dockerfile  web/Dockerfile  web/nginx.conf  *.dockerignore
          Makefile  .env.example  scripts/**  .github/workflows/**
          api/ops/**               telemetry collectors, cost accounting
          api/routes/ops.py
          infra/**
FORBIDDEN api/pipeline/**  api/graph/**  api/query/**  web/src/**
```

### Orchestrator (you, the lead session)
Owns everything the agents are forbidden from: `api/db/models/**`,
`api/db/migrations/**`, `api/contracts/**`, `api/routes/__init__.py`,
`api/tasks.py`, `api/config/settings.py`, `design/**`,
`web/src/design-system/tokens.ts`, `plans/**`, `BRANCH.md`, `traverse-prd.md`.
Runs the contract freeze, the merge train, and the retro.

**The design canvas is an orchestrator artifact.** Visual design lives in a
Claude Design canvas (an Artifact URL recorded in `design/DESIGN.md`); the
*contract* FE1 builds against is `design/DESIGN.md` §4 plus the frozen
`tokens.ts`. FE1 reads both, implements, and files a DCR rather than
improvising when they disagree. See [design/DESIGN.md](design/DESIGN.md).

---

## 3. Worktree layout

Worktree **directories are persistent** across sprints — they hold `.venv`,
`node_modules`, and the Docling/HF model cache, and rebuilding those every
sprint wastes 10+ minutes per agent. **Branches are per-sprint** and deleted
after merge.

```
/home/prinzz/main/my-projects/traverse/          ← ai-master, integration, orchestrator
/home/prinzz/main/my-projects/traverse-wt/
    be1/    ← ai/be1/sprint-N-<slug>
    be2/    ← ai/be2/sprint-N-<slug>
    fe1/    ← ai/fe1/sprint-N-<slug>
    do1/    ← ai/do1/sprint-N-<slug>
```

The worktree root is a **sibling** of the repo, not `.worktrees/` inside it —
nested worktrees confuse Docker build contexts, `uv`, and Vite's file watcher.

### First-time creation (once, ever)

```bash
cd /home/prinzz/main/my-projects/traverse
mkdir -p ../traverse-wt
for a in be1 be2 fe1 do1; do
  git worktree add -b ai/$a/sprint-1-foundations ../traverse-wt/$a ai-master
done
git worktree list
```

### Every subsequent sprint (orchestrator, after the freeze is merged)

```bash
cd /home/prinzz/main/my-projects/traverse
SPRINT=3; SLUG=characters
for a in be1 be2 fe1 do1; do
  git -C ../traverse-wt/$a fetch origin 2>/dev/null || true
  git -C ../traverse-wt/$a checkout ai-master
  git -C ../traverse-wt/$a merge --ff-only ai-master
  git -C ../traverse-wt/$a checkout -b ai/$a/sprint-$SPRINT-$SLUG
done
```

### Per-agent environment bootstrap

```bash
# backend agents (be1, be2)
cd ../traverse-wt/be1/api && uv sync

# frontend agent
cd ../traverse-wt/fe1/web && pnpm install

# devops agent works against the integration checkout for compose runs
```

---

## 4. Environment isolation

Infra containers are **singletons on the host**, started once from the
integration checkout and shared by all worktrees. Only one GPU exists, so only
one vLLM can run. Isolation happens at the **database and port** level, not the
container level.

| Resource | Host port | Isolation |
|---|---|---|
| Postgres (pgvector) | 5433 | Separate database per agent: `traverse_be1`, `traverse_be2`, `traverse_int` |
| Neo4j Community | 7474 / 7687 | **Community edition supports one database.** `be2` has exclusive write access; `do1` reads it during integration. `be1` and `fe1` never touch it. |
| vLLM (Qwen3-8B-AWQ) | 8080 | Shared. `be1` and `be2` both call it — see §9 contention note. |
| RabbitMQ | 5672 / 15672 | Separate vhost per agent: `/be1`, `/be2`, `/int` |
| MinIO | 9000 / 9001 | Separate bucket per agent: `traverse-be1`, `traverse-be2`, `traverse-int` |
| Langfuse | 3000 | Shared; agents tag traces with `session_id=<agent>` |
| FastAPI | 8000 int · 8001 be1 · 8002 be2 · 8003 fe1-mock | one per agent |
| Vite dev server | 5173 fe1 · 5174 int | |

Each worktree gets its own `api/.env` written by the agent from
`.env.example`, with `POSTGRES_DB_STRING`, `RABBITMQ_URL`, and `API_PORT`
pointed at its own slice. `.env` is gitignored and must never be committed.

Create the per-agent databases once:

```bash
for a in be1 be2 int; do
  docker compose exec -T db psql -U postgres -c "CREATE DATABASE traverse_$a;" || true
  docker compose exec -T db psql -U postgres -d traverse_$a -c "CREATE EXTENSION IF NOT EXISTS vector;"
done
```

---

## 4a. `master` is human. `ai-master` is ours.

**No agent work reaches `master` — not a commit, not a merge, not a tag.**
Everything written by an agent lands on **`ai-master`**, so the provenance of
every line is legible from the branch graph alone.

```
master      ← human-authored only. Untouched by this workflow.
ai-master   ← the integration branch. Contract freezes, merge trains, tags.
ai/<agent>/…← per-sprint agent branches, cut from and merged into ai-master.
```

The merge train (§7) targets `ai-master`. Worktrees are cut from `ai-master`.
Agents rebase onto `ai-master`. The contract freeze lands on `ai-master`.

Promoting `ai-master` into `master` is a **human decision**, made by opening a
pull request and reviewing it — never by an agent, and never as a step in a
sprint. If you are an agent reading this: you do not merge to `master`, and you
do not push to it.

## 5. Branch naming and commits

```
ai/<agent>/sprint-<N>-<slug>        normal sprint work
ai/<agent>/fix-<short-desc>         hotfix on a merged sprint
ai/orchestrator/sprint-<N>-freeze   the contract freeze
```

**Every branch an agent creates starts with `ai/`.** No exceptions, including the
orchestrator's freeze branches — everything in this project is written by an
agent, and the prefix is what makes that legible afterwards. It is not
decoration: it gives one glob for tooling.

```bash
git branch --list 'ai/*'                    # every agent branch
git branch -d $(git branch --list 'ai/*/sprint-3-*')   # clean up after a merge train
```

DO1 wires the prefix into branch protection and CI (`on.push.branches: ['ai/**']`),
and the merge train refuses a branch that does not match — a human-authored
branch merging through the agent train is a review-process bug worth catching.

Commit messages: conventional commits, scoped to the owned area, referencing
the story ID from the sprint plan.

```
feat(pipeline): persist chapter segmentation with page ranges [S2.3]

Closes S2.3. Chapter rows now carry detection_method so the eval harness
can separate regex hits from LLM-classified headings.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
```

Commit at every completed story, minimum once per working day. An agent that
has not committed by end of Day 3 is blocked and must escalate.

---

## 6. Sprint cadence (5 days)

| Day | Activity | Who |
|---|---|---|
| **1** | **Contract freeze.** Orchestrator lands models, the sprint's single Alembic migration, Pydantic contracts, route stubs, task-name registry, settings keys on `ai-master`. Sprint plans reviewed. Worktree branches cut from the frozen `ai-master`. | Orchestrator |
| **2–4** | **Parallel build.** Four agents work in their worktrees against the frozen contracts. Daily async standup written to `plans/sprint-N/STANDUP.md`. | 4 agents |
| **5 am** | **Merge train** (§7), then integration run on the seeded corpus. | Orchestrator + agents on call |
| **5 pm** | **Demo** against the sprint's demo script, then **RETRO.md**. | All |

Day 1 is deliberately not a build day. The freeze is what buys three
conflict-free days, and compressing it is the single most reliable way to lose
Day 5 to merge conflicts.

---

## 7. The merge train

Fixed order, every sprint. The order is dependency-driven, not political.

```
1. do1   infra and CI first — everyone else's integration run needs it green
2. be1   deepest dependency: nothing downstream exists without chunks
3. be2   consumes be1's tables; rebases onto be1's merge
4. fe1   consumes the API; conflicts least, so it absorbs any drift
```

Protocol per agent, in order:

```bash
cd ../traverse-wt/be1
git fetch origin && git rebase ai-master     # agent resolves its own conflicts
uv run pytest api/tests -q                   # must be green post-rebase
git push -u origin ai/be1/sprint-3-characters

cd /home/prinzz/main/my-projects/traverse   # on ai-master
git merge --no-ff ai/be1/sprint-3-characters
make test-integration                        # must be green before next merge
```

Rules:

- **Rebase onto `ai-master`, never merge `ai-master` into your branch.** Keeps history
  linear and makes the conflict surface visible.
- **The agent resolves its own conflicts.** The orchestrator never guesses at
  another agent's intent.
- **A red merge blocks the train.** The offending agent fixes forward on its
  branch; the train does not proceed around it.
- After all four merge: `git tag sprint-N` and delete the four sprint branches.

---

## 8. Schema Change Requests

An agent that needs a column, table, index, or contract field mid-sprint:

1. **Does not** write a migration or edit a model.
2. Appends to `plans/sprint-N/SCR.md`:

```markdown
### SCR-3 · be2 · 2026-09-24T14:10
**Need:** `relation.assertion_type` needs an `inferred_from` int (evidence count)
**Why:** confidence weighting in F3.2 cannot be computed post-hoc without it
**Blocking:** yes — S4.5 cannot complete
**Proposed:** `ALTER TABLE relation ADD COLUMN inferred_from integer NOT NULL DEFAULT 1`
```

3. Orchestrator lands it on `ai-master` as migration `NNNN`, announces it.
4. All four agents `git rebase ai-master` at their next natural break.

Non-blocking SCRs are batched into the next sprint's freeze. Blocking SCRs are
landed within the hour. **Two blocking SCRs from the same agent in one sprint is
a retro action item** — it means the freeze was under-specified.

**Design Change Requests (`DCR-`)** follow the identical protocol for anything in
`design/**` or `tokens.ts`. FE1 never edits a token to unblock itself; a design
token changed in a worktree is a divergence nobody sees until it ships.

---

## 9. Known contention and how it is handled

| Contention | Handling |
|---|---|
| **Single GPU, shared vLLM** | `be1` (chapter classification, pass-1) and `be2` (pass-2) both hit `:8080`. vLLM runs `--max-num-seqs 16` with continuous batching, so concurrent load degrades latency, not correctness. Agents must not benchmark on a shared server — performance numbers are taken during integration only, and any timing claim from a worktree is invalid. |
| **Neo4j single database** | `be2` exclusive. `be2` prefixes nothing; instead it must implement `graph.reset(book_id)` from day one so integration can rebuild cleanly from Postgres. |
| **Embedding model memory** | BGE-M3 on CUDA from two worker processes will OOM a consumer card. Backend agents set `EMBEDDING_DEVICE=cpu` in worktree `.env` for unit work; GPU embedding is exercised in integration only. |
| **Docling model cache** | Shared read-only at `~/.cache/docling` and `~/.cache/huggingface`. Never let two agents run `download_models()` concurrently — `do1` warms it in Sprint 1 and it stays warm. |

---

## 10. Definition of Done

A story is done when **all** hold:

- [ ] Code merged to `ai-master` via the merge train
- [ ] Unit tests for the new path, passing
- [ ] The PRD acceptance criterion it maps to is demonstrably met, with the
      command or URL that shows it written into the sprint README
- [ ] No new `ruff` (backend) or `oxlint` (frontend) violations
- [ ] Contracts consumed by another agent are documented in
      `plans/sprint-N/HANDOFF.md`
- [ ] Langfuse trace exists for any new LLM call path
- [ ] Nothing hardcodes a local absolute path (`/home/prinzz/...` is a review
      failure — see the existing `CACHE_DIR` in `chunking.py`)
- [ ] **The matching `codebase-memory` map is updated in the same commit** when
      the change alters the schema, a stage boundary, an ontology predicate, an
      SSE event, or the service topology — and any entry the sprint moved from
      planned to built is flipped from `S<n>` to `Built`

A **sprint** is done when the demo script in `plans/sprint-N/README.md` runs end
to end on the integration checkout from `docker compose up`, and `RETRO.md` is
written.

---

## 10a. Read before you explore

Every agent reads three things before touching code, and none of them is the
codebase:

1. **[AGENTS.md](AGENTS.md)** plus the stack file for where you are working —
   [api/AGENTS.md](api/AGENTS.md) or [web/AGENTS.md](web/AGENTS.md).
2. **This file**, for ownership and the merge protocol.
3. **[`.agents/skills/codebase-memory`](.agents/skills/codebase-memory/SKILL.md)** —
   a topic → map-file index covering the data model, ingestion, characters and
   graph, query path, LLM runtime, web app, and infra.

**Do not launch explore or general-purpose subagents to learn how this codebase
works.** A broad explore pass costs tens of thousands of tokens and returns a
worse answer than a 90-line map written by whoever built the subsystem —
multiplied by four agents across eight sprints, it is the largest avoidable cost
in the project. Read the map, confirm the specific symbol you intend to edit with
a targeted `Grep`, then work.

The maps mark every symbol `Built`, `S<n>` (lands in sprint *n* — **do not grep
for it**), or `Broken` (a known defect, named so nobody debugs it twice). That
status column is what makes the maps worth more than the code.

The corollary is the maintenance duty in §10: a map that drifts is worse than no
map, because agents trust it.

## 11. Ceremonies

**Daily standup (async, written).** Each agent appends to
`plans/sprint-N/STANDUP.md`: what landed, what is next, what is blocked. Three
lines. An agent blocked for more than half a day escalates to the orchestrator
rather than working around it.

**Demo (Day 5).** Run the sprint README's demo script literally, on the
integration checkout, from a cold `docker compose up`. "It works on my worktree"
is not a demo. A failed demo does not fail the sprint — it becomes the first
retro item and the first story of the next sprint.

**Retro (Day 5).** `plans/sprint-N/RETRO.md` from `plans/RETRO-TEMPLATE.md`.
Every retro produces **action items with an owner and a target sprint**, and the
next sprint's plan must visibly absorb them. A retro that produces no change to
the next plan was not a retro.

---

## 12. Sprint map

| Sprint | Theme | PRD phases | Gate | Demo |
|---|---|---|---|---|
| 1 | Foundations & contracts | 0, 1.5 | | Cold `docker compose up` brings the full stack green; web shell renders against the contract API |
| 2 | Ingestion pipeline | 1, 1.5 | | Upload a real novel, watch every stage complete, inspect chapters and chunks with page provenance |
| 3 | Character extraction | 2 | | Upload *Pride and Prejudice*, get an accurate roster with aliases, tiers, and first-appearance pages |
| 4 | Relationship graph | 3 | **SHIP GATE** | The character graph, every edge click-through to the pages that prove it |
| 5 | Series & reconciliation | 5 | | Upload *Anne of Green Gables* 1–3 into one project: one Anne, an appearance strip across volumes, an Anne↔Gilbert arc spanning three books |
| 6 | Query & citations | 6 | | Ask "how does Elizabeth know Mr Darcy", get a cited answer, click to the page |
| 7 | Human review queue | 7 | | Pipeline pauses on the two Catherines, human resolves, graph updates and cascades |
| 8 | Evals & spoiler mode | 8 | | Ablation table populated with real numbers; the reading-position control visibly shrinks the graph |
| 9 | Ops, hardening & GTM | 9 | | Ops dashboard with live cost/latency; public demo deployed; writeup published |

Full backlog with PRD requirement traceability: `plans/BACKLOG.md`.

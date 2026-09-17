# Traverse delivery plan

Nine one-week sprints taking [traverse-prd.md](../traverse-prd.md) from its
current state (Docling parsing, chapter detection, embeddings, similarity
search) to the full product: an evidence-anchored character knowledge graph with
page-exact citations, a human review loop, published evals, and a deployed
public demo.

Read [BRANCH.md](../BRANCH.md) first. It defines the worktree layout, directory
ownership, and the merge train. Nothing in this folder works without it.

---

## How to run a sprint

```
Day 1  Orchestrator: contract freeze on ai-master, cut four branches
Day 2  Agents: build       ──┐
Day 3  Agents: build         ├─ four worktrees, zero shared files
Day 4  Agents: build       ──┘
Day 5  Merge train → integration run → demo → RETRO.md
```

**Day 1, orchestrator, on `ai-master`:**

```bash
cd /home/prinzz/main/my-projects/traverse
# 1. land the sprint's models, single migration, contracts, route stubs
# 2. verify
cd api && uv run alembic upgrade head && uv run pytest tests/contracts -q
# 3. commit and cut branches
git commit -am "chore(orchestrator): sprint-N contract freeze"
SPRINT=N SLUG=<slug>
for a in be1 be2 fe1 do1; do
  git -C ../traverse-wt/$a checkout ai-master && git -C ../traverse-wt/$a merge --ff-only ai-master
  git -C ../traverse-wt/$a checkout -b ai/$a/sprint-$SPRINT-$SLUG
done
```

**Day 2, launching the agents.** Each agent gets exactly one plan file as its
brief, plus `BRANCH.md`. Launch all four in a single message so they run
concurrently:

> Read, in order: `AGENTS.md`, `api/AGENTS.md` (or `web/AGENTS.md` if you are
> fe1), `BRANCH.md`, and `plans/sprint-N/backend-1.md`. You are Backend
> Engineer 1. Your worktree is `../traverse-wt/be1` on branch
> `ai/be1/sprint-N-<slug>`.
>
> **Before exploring the codebase, use the `codebase-memory` skill**
> (`.agents/skills/codebase-memory/SKILL.md`) — match your task to a topic, read
> that one map file, then confirm specific symbols with a targeted Grep. Do not
> launch explore subagents for areas the maps already cover. If a map is wrong,
> fix it in the same commit as the code.
>
> Implement every story in your plan. Stay inside your owned paths — if you need
> anything outside them, file an SCR per BRANCH.md §8 rather than editing it.
> Commit per story.

**Day 5:** run the merge train (BRANCH.md §7), then the demo script in
`plans/sprint-N/README.md`, then write `RETRO.md`.

---

## Sprint index

| Sprint | Theme | Gate | Plan |
|---|---|---|---|
| 1 | Foundations & contracts | | [sprint-1/](sprint-1/) |
| 2 | Ingestion pipeline | | [sprint-2/](sprint-2/) |
| 3 | Character extraction | | [sprint-3/](sprint-3/) |
| 4 | Relationship graph | **SHIP GATE** | [sprint-4/](sprint-4/) |
| 5 | Series & reconciliation | | [sprint-5/](sprint-5/) |
| 6 | Query & citations | | [sprint-6/](sprint-6/) |
| 7 | Human review queue | | [sprint-7/](sprint-7/) |
| 8 | Evals & spoiler mode | | [sprint-8/](sprint-8/) |
| 9 | Ops, hardening & GTM | | [sprint-9/](sprint-9/) |

Each sprint folder contains:

```
README.md       goal, scope, demo script, definition of done
backend-1.md    BE1's brief — hand this to the agent verbatim
backend-2.md    BE2's brief
frontend-1.md   FE1's brief
devops-1.md     DO1's brief
STANDUP.md      written during the sprint
SCR.md          schema change requests raised during the sprint
HANDOFF.md      contracts one agent produced for another
RETRO.md        written on Day 5
```

---

## Planning horizon

Sprints 1–4 are specified to task level. Sprints 5–8 are specified to story
level with acceptance criteria, and are **deliberately less detailed** — they
will be re-planned at each sprint boundary to absorb retro action items and what
the eval numbers actually say. Planning sprint 8 to task level today would be
fiction, and rewriting it four times is waste.

The contract that does not move is the sprint *goal* and its demo. Those are
commitments. The task breakdown inside a sprint is the agents' to renegotiate.

---

## Traceability

[BACKLOG.md](BACKLOG.md) maps every PRD functional requirement (F1.1 … F7.4) to
the sprint and agent that delivers it. Nothing in the PRD is unassigned, and
anything deliberately cut is listed there with the reason. When a story is
descoped mid-sprint, it moves in BACKLOG.md — it does not silently vanish.

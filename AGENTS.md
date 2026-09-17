# Agent Instructions

Coding-style and workflow instructions for AI agents working in this repository.
Tool-agnostic: readable by any agent that loads repo context (IDE assistants, CLI
agents, CI bots).

Traverse is a monorepo with two stacks. **Read the one you are working in:**

| Stack | Path | Conventions |
| ----- | ---- | ----------- |
| Backend — Python / FastAPI / Celery / LangGraph | `api/` | [api/AGENTS.md](api/AGENTS.md) |
| Frontend — React / TypeScript / Chakra | `web/` | [web/AGENTS.md](web/AGENTS.md) |

This file covers what applies to both.

---

## Before you explore, read the memory

**Do not launch explore or general-purpose subagents to learn how this codebase
works.** Use the [`codebase-memory`](.agents/skills/codebase-memory/SKILL.md)
skill: a routing index from topic → one map file. A broad explore pass costs tens
of thousands of tokens and returns a worse answer than a 90-line map that was
written by whoever built the subsystem.

The protocol is:

1. Match your task to a topic in the memory skill's table.
2. Read **only** that file.
3. Confirm any symbol you will edit with a targeted `Grep` / `Read`.
4. Explore broadly only when the map plus a symbol check still leave a gap.
5. **If the map is wrong, fix it in the same commit that fixes the code.**

Step 5 is not optional. A memory file that drifts is worse than none, because
agents trust it.

## Working agreement

This project is built by four parallel agents in git worktrees. Before doing
anything, read [BRANCH.md](BRANCH.md) — it defines directory ownership, branch
naming, the merge train, and the Schema Change Request protocol.

The rules that matter most for not breaking other agents:

- **Stay inside your owned paths.** If you need a file outside them, file an SCR
  (BRANCH.md §8). Do not edit it "just this once".
- **Never write an Alembic migration.** One migration per sprint, authored by the
  orchestrator at the contract freeze. Two agents writing `0006` produces a
  branch Alembic refuses to run.
- **Never edit `api/contracts/**`, `api/db/models/**`, `design/**`, or
  `web/src/design-system/tokens.ts`.** These are frozen; changing one in a
  worktree is a divergence nobody sees until it ships.
- Branch names start with `ai/` — `ai/<agent>/sprint-<N>-<slug>`.

## Comments

- End every comment with a full stop (`.`).
- **Default to no comment.** Do not add one for every line or small change just
  because the code changed — most lines should carry none.
- Comment only genuinely non-obvious logic: a subtle invariant, a workaround for
  an external gotcha, a non-obvious algorithm. Never restate what the code says.
- No module-level file-purpose banners before imports.
- No comments on class definitions.

Domain-specific exception: this codebase encodes decisions that are **wrong in
non-obvious ways if changed**, and those earn a comment. For example, why the
pass-2 roster prefix must be byte-identical across calls (vLLM prefix caching),
or why an edge cannot be written without evidence. State the consequence, not the
mechanism.

## Absolute paths

**No absolute host path may appear anywhere in the repo.** `grep -rn "/home/" .`
must return nothing outside `.gitignore`d files. Everything runs in containers;
a hardcoded `/home/prinzz/...` cache directory is a broken build for everyone
else and a review failure.

## No secrets

`.env` is gitignored and stays that way. Every settings key belongs in
`.env.example` with a working local default or an obvious placeholder. Never
commit a token, key, or password — including in a test fixture or a compose
file.

## Testing

Run tests through the `test` service in `docker-compose.yml`, never `pytest` or
`pnpm test` directly on the host — the container matches CI (env vars, Postgres
version, offline model cache).

```bash
docker compose --profile test run --rm test                 # backend
docker compose --profile test run --rm test-web             # frontend
```

**Never run the full suite without asking first.** After a change, prefer a
targeted run scoped to the affected files:

```bash
docker compose --profile test run --rm test pytest api/tests/pipeline/test_chunking.py -v
```

Ask before running everything — let the developer request a full run when they
want one.

Tests must not reach the network. Model downloads are pre-warmed into a shared
volume (`make warm-models`); tests run with `MODELS_OFFLINE=1`.

## Commits

Conventional commits, scoped to the area you own, referencing the story ID from
your sprint plan.

```
feat(pipeline): persist chapter segmentation with page ranges [S2.3]

Chapter rows now carry detection_method so the eval harness can separate
regex hits from LLM-classified headings.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
```

Commit at every completed story, minimum once per working day.

## Agent configuration (`.agents/`)

Portable, version-controlled context for coding agents:

| Path | Purpose |
| ---- | ------- |
| `AGENTS.md` (root) | Always-on conventions shared by both stacks — the primary entry point |
| `api/AGENTS.md`, `web/AGENTS.md` | Stack-specific style |
| `.agents/rules/*.md` | Scoped rules — architecture, domain boundaries, path-specific patterns |
| `.agents/skills/*/SKILL.md` | Named workflows and the codebase memory index |

**Separation of concerns**

- **`AGENTS.md`** — how to write code.
- **`.agents/rules/`** — what the system is and how subsystems connect; applied
  via `scope` / `paths` frontmatter.
- **`.agents/skills/codebase-memory/`** — where things actually are, so nobody
  has to go looking.

Do not duplicate coding-style guidance in rule files; link here instead.

### Rule files

Markdown with YAML frontmatter. Copy `.agents/rules/_template.md` for new rules.

```yaml
---
description: One line — scope and intent (required, under ~120 chars).
scope: always          # always | paths | on-demand
paths: api/pipeline/**/*.py   # required when scope is paths
---
```

| Field | Required | Notes |
| ----- | -------- | ----- |
| `description` | Yes | Imperative. State *when* and *what*. |
| `scope` | Yes | `always` — every session; `paths` — when matching files are in context; `on-demand` — when the agent judges it relevant from `description`. |
| `paths` | When `scope: paths` | One glob or comma-separated list. |

Filenames are kebab-case; `_` prefix is for templates only. One primary concern
per file — split when a rule exceeds ~100 lines or mixes unrelated topics.

### Skills

| Skill | Purpose |
| ----- | ------- |
| `codebase-memory` | Topic → map file routing index. **Use instead of explore subagents.** |

`.claude/skills/codebase-memory` symlinks to `.agents/skills/codebase-memory`, so
Claude Code discovers it natively while the canonical copy stays tool-agnostic.

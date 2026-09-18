# Sprint 1 Retrospective

**Dates:** 2026-09-17 → 2026-09-18
**Goal:** a cold `docker compose up` brings the entire stack green, the v2 data model is migrated, every cross-agent contract is frozen, and the web shell renders real (empty) data from the real API.
**Outcome:** **Met** — after four fixes found by actually running the demo script cold, not assumed from per-branch tests.

---

## 1. Delivered

| Story | Owner | Status | PRD ref | Notes |
|---|---|---|---|---|
| S1.1 | be1 | Done | — | Worker bootstrap, stage recorder. `stage()` correctly leaves a `running` row on a killed process. |
| S1.2 | be1 | Done | F1.1–1.3 | Config-driven chunker. Found + fixed: RapidOCR reachable by default (network+GPU in a worktree), a ~1-in-8 Docling cold-start page-drop now raised as retryable. |
| S1.3 | be1 | Done | — | Repository layer. 500 chunks insert in ~0.1s (budget 2s). |
| S1.4 | be1 | Done | — | `GET /projects`, `/projects/{id}`, `/books/{id}`, `/books/{id}/status`. |
| S1.4 | be2 | Done | F5.1 | Neo4j driver lifecycle: single connection, `ServiceUnavailable` backoff, restart-survivable (verified against a real container restart). |
| S1.5 | be2 | Done | F3.1 | Ontology as data — 32 predicates, 5 families, 17 legal transitions, in YAML. |
| S1.6 | be2 | **Done — the gate** | F5.1 | Checkpointer kill-and-resume. Real subprocess, real `SIGKILL`, fresh process resumes with state intact. Re-verified independently on the merged tree at demo time. |
| S1.7 | be2 | Done | — | `/graph/ontology` live; character/graph reads against real (empty) Postgres. |
| S1.8 | fe1 | Done | — | App shell, full route table, literary theme, dark mode, all 7 primitives incl. `<PageRef>` to spec. |
| S1.9 | fe1 | Done | — | Typed client generated from the live 33-path contract; one hook per endpoint. |
| S1.10 | fe1 | Done | F1.1 | Library, upload, ingestion stepper. The 501 renders as a real error surface. |
| S1.11 | do1 | Done* | NFR-deploy | Full compose topology. *RabbitMQ 4 queue-type fix found and fixed same-day. |
| S1.12 | do1 | Done* | — | Dockerfiles, behavioural healthchecks. *Two gaps found at demo time, see §4. |
| S1.13 | do1 | Done | — | Makefile, `.env.example`, bootstrap script, orchestrator-only revision guard. |
| S1.14 | do1 | Done | — | CI: ruff, pytest, web build, compose smoke — 4 parallel jobs. |
| S1.15 | do1 | Done | — | Model cache warm-up, `MODELS_OFFLINE=1` wiring. |

**Demo result:** **Passed**, on the second attempt. First cold run failed at `make up` (celery-worker never reached healthy). Root-caused and fixed live; full script green afterward. See §4 for what broke and why none of the per-agent test suites could have caught it.

Command log: this retro; no separate recording taken.

---

## 2. Metrics

| Metric | Target | Actual | Δ |
|---|---|---|---|
| Stories completed | 15/15 | 15/15 | — |
| Merge-train conflicts | 0 | 8 (6 shared-doc, 1 dependency, 0 code-logic) | over, but see §3 |
| Blocking SCRs raised | ≤ 1 | 0 filed as blocking; **4 found and fixed directly at demo time instead** | see §4 |
| Test suite runtime (backend) | — | 12.4s (137 tests) | |
| Test suite runtime (frontend) | — | 3.0s (99 tests) | |
| Cold `docker compose up` wall clock | < 5 min (NFR-deploy) | ~7 min image build + ~4 min model warm-up on first run | miss on a fully cold cache — see A-1.4 |
| Agent session interruptions (rate limit) | 0 | 2 rounds, all 4 agents both times | see §3, §5 |
| Work lost to interruption | 0 | 0 (round 2) / ~1 session (round 1, uncommitted) | see §3 |

---

## 3. What went well

- **Directory ownership genuinely worked.** Zero merge conflicts touched two agents' *code*. Every conflict was in a shared append-only doc (`HANDOFF.md`, `SCR.md`, `STANDUP.md`) that multiple agents wrote to concurrently from the same base — an artifact of the append pattern, not of scope bleed. Not one agent edited a file outside their owned paths without filing an SCR first.
- **The commit-cadence fix held on the second interruption round.** Round 1: all four agents were killed by a rate limit with several stories batched into uncommitted trees — real risk of losing a full session. Told them explicitly to commit as soon as a file compiles and lints. Round 2: same four-agent rate limit hit again, and this time be1 (8 commits), fe1 (7), do1 (12) all had clean or near-clean trees. Nothing was at risk the second time.
- **Real bugs were found by tests, not by luck.** be1's chunker tests caught a ~1-in-8 Docling cold-start page drop and RapidOCR reaching the network by default. fe1's route-smoke test (mount every route, fail on any console error) caught a real Chakra v3 `<Icon>` default. be2's checkpointer test is a genuine kill-and-resume, not a mock.
- **SCR/DCR discipline scaled.** 9 SCRs and 4 DCRs filed across the sprint, every one with a "why," a blocking call, and a proposed fix — none silently worked around in a way that hid the gap.
- **Frozen task-name-as-string decoupling worked exactly as designed.** be1 and be2 never touched each other's task modules; `import_task_modules()` tolerating a missing module meant a 6-of-9-stage worker booted correctly rather than refusing to start.

## 4. What went wrong

- **The merge train verified each branch, not the merged whole, until the demo step caught it.** Four bugs existed only in the *combination* of do1's compose file with be1's worker module, and none of them could show up in any single agent's test suite:
  1. Compose pointed Celery at `-A api.tasks` (defines the app, imports nothing); be1's real entry point was `api.workers.app` (imports task modules). Every stage was silently unregistered — the worker would have booted and accepted zero real work.
  2. `/health` still returned the frozen stub in the running container, despite do1 writing real probes and leaving an exact wiring snippet in HANDOFF.md — a four-line change nobody had landed.
  3. The documented `CELERY_REQUIRE_STAGES=0` escape hatch was hardcoded under the `test` profile only; the actual `celery-worker` service never read it. The comment was right; the mechanism it described didn't exist.
  4. The worker healthcheck's two sequential `inspect()` calls have no `destination=`, so each waits its *full* timeout regardless of how fast the single worker replies — 10s + 10s reliably exceeded the container's 20s window.

  *What would have prevented this:* nothing in the current process, short of literally running the demo script earlier. This is why Day 5's demo step exists as a mandatory gate rather than "tests passed, ship it" — and why it should run **before**, not after, the tag.

- **I (orchestrator) fixed these directly on `ai-master` rather than routing them back through an agent.** Correct given all four agents' sprints were already merged and closed, but it means the fixes carry no agent attribution and no agent learned from the failure. Worth deciding explicitly whether "orchestrator fixes post-merge integration bugs" is the standing rule or whether a fifth short-lived agent turn should own it.

- **`docker compose down -v` for the cold-state test destroyed local dev-database state I then had to notice and repair.** The container volume wipe also reset `traverse_int` (the orchestrator's own local pytest target) to empty, because the compose `migrate` service only migrates the containers' own `postgres` database, not the separately-provisioned per-agent databases. Not a bug — by design, two different environments for two different purposes — but it cost a debugging detour to realize that, and the distinction isn't written down anywhere.

- **Cold cache made the ≤5-minute NFR-deploy target miss badly** (~11 minutes: image build + model warm-up). The target assumes a *warm* model cache; it says so in NFR-deploy's own wording ("on a warm cache") but the demo script's literal `git clean -xfd && docker compose down -v` invites exactly the cold state where it can't be met. The script and the target disagree with each other.

## 5. What we learned

- **Two rate-limit interruptions across four parallel Opus agents is now the expected shape of a sprint**, not an anomaly. Plan the cadence assuming it happens at least once, not as a contingency.
- **`celery.control.inspect()` waits its full timeout by design** when no `destination` is given — it cannot know how many workers might still reply, so it never returns early just because the one worker on this host already answered. This will bite again anywhere else in the codebase that calls `inspect()` without a destination and assumes it returns fast.
- **A per-file-ignore for `ruff check` does not cover `ruff format`.** Two agents (be2 and do1) independently discovered this and independently fixed it the same way, which is a good sign the fix was obviously correct, but also means the freeze should have covered it originally.
- **A shared append-only doc from a common ancestor is *always* an add/add conflict once two agents write to it in the same sprint window**, even though the content itself is compatible. This isn't a Git problem to route around — it's the expected shape, and the resolution (concatenate, renumber colliding SCR/DCR ids) is now a known five-minute step, not a surprise.

---

## 6. Action items

| # | Action | Owner | Target | Done? |
|---|---|---|---|---|
| A-1.1 | Run the sprint's demo script **before** tagging, not as a final formality — treat a demo failure as normal, not exceptional | orchestrator | Sprint 2 | Adopted this retro |
| A-1.2 | Seed `plans/sprint-N/HANDOFF.md`, `SCR.md`, `STANDUP.md` as empty templated files at the contract freeze, so agents append to a common base instead of each creating the file fresh (removes the add/add conflict at its root) | orchestrator | Sprint 2 | |
| A-1.3 | Add an integration-level check to CI that boots the real compose stack and asserts `celery inspect registered` against the actual worker command in the actual compose file — not just a unit test against `api/workers/app.py` in isolation | do1 | Sprint 2 | |
| A-1.4 | Reconcile NFR-deploy's "<5 min" with the demo script's literal cold-volume wipe — either the demo script warms the cache first, or the target is explicitly "warm cache only" everywhere it's stated | orchestrator | Sprint 2 | |
| A-1.5 | Write down, in `.agents/skills/codebase-memory/infra-topology.md`, that the per-agent databases (`traverse_be1/be2/int`) and the containers' own `postgres` database are separate and serve separate purposes — this cost a debugging detour once already | do1 or orchestrator | Sprint 2 | |
| A-1.6 | Decide the standing rule for post-merge integration bugs found at the demo step: orchestrator fixes directly (current practice) vs. a short-lived fix-forward agent turn per bug | human | Before Sprint 2 close | |
| A-1.7 | Resolve the accessibility-gating contradiction (`PRODUCT.md`: best-effort/not gated vs. `plans/sprint-9/frontend-1.md`: gated in CI) — flagged independently by do1 in both rounds | human | Before Sprint 9 | |

**Carried from previous retro:** none — this is Sprint 1.

---

## 7. PRD amendments

None. Every finding this sprint was implementation/process, not a wrong product assumption. `traverse-prd.md` is unchanged.

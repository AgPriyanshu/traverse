# Sprint 9 Retrospective

**Dates:** 2026-09-28 → 2026-09-29
**Goal:** the ops dashboard proves production experience, the demo is publicly reachable, and the writeup is published.
**Outcome:** The engineering is done and real — live routing switching, real telemetry, real upload privacy/quota enforcement, a real accessibility pass. The demo is deliberately **not** publicly reachable yet: that decision needs the user, not an agent, and is carried forward rather than done unilaterally. The recording and writeup are orchestrator/human work, not yet started.

## 1. Delivered

| Story | Owner | Status | Notes |
|---|---|---|---|
| S9.1–S9.3 | do1 | Built, merged, verified | Cost/performance/pipeline-health telemetry reading real `IngestionStage`/`QueryLog` rows, not synthetic data. Celery queue depth honestly documented as "what workers currently hold," not a true broker backlog. |
| S9.4 | do1 | Built, merged, verified locally, **deliberately not deployed** | Production compose overlay, TLS, rate limiting, CPU-only profile, budget guard — verified via config merge, `nginx -t`, and a standalone TLS/rate-limit proof. No cloud host, domain, or real cert; going live is the user's call, per explicit instruction this sprint. |
| S9.5 | do1 → be1 (fast-follow) | Built, merged, **reconciled** | Quota/TTL/public-domain guard built independently of be1's session isolation work; the two modules managed the same `UploadSession` table without knowing about each other. Reconciled in a same-day fast-follow (`749c409`): session creation stays be1's, quota/abuse checks are do1's, wired into the real upload route with real 429/413/422 HTTP tests. A gap between the two TTL-sweep mechanisms' delete depth remains, filed as SCR-2. |
| S9.6–S9.7 | be2 | Built, merged, verified | Live routing-policy switching meets F7.3's literal acceptance criterion (a PUT changes the very next call in the same process, no restart). Frontier path with two fallback layers, both verified with fakes since no real key exists in this environment. Fixed the real `greenlet_spawn` bug flagged in Sprint 8, and a real residency-floor bypass (local-only previously didn't apply to every purpose). |
| S9.8–S9.9 | be1 | Built, merged, verified | Real cross-session isolation (404 for a private project accessed from another session, never 403 — a private project must be indistinguishable from nonexistent), real deletion across Postgres/MinIO/Langfuse/Neo4j. Found and fixed a real pre-existing cross-project pooling bug in the reingest fallback. OCR formally deferred — no offline model cache entry or scanned-PDF fixture exists, and Sprint 8 didn't leave room either. |
| S9.10–S9.13 | fe1 | Built, merged, verified | Ops dashboard including the PRD's "closing-argument" routing control; inference-mode labelling; a real axe-core accessibility pass finding and fixing three real bugs; public landing state. Two real `tsc` errors slipped past this agent's own build check and were caught and fixed at the merge train (see §3). |

**Demo result:** Not run as a single live end-to-end pass. Each demo-script beat has real, independent evidence (routing-policy live switch, upload-guard HTTP rejection tests, axe-core pass) rather than one recorded walkthrough — the actual 90-second recording (S9.14) has not been attempted yet.

## 2. DoD status, honestly

| DoD line item | Status |
|---|---|
| Public demo reachable, no signup, working on a phone, rate-limited | **Not met, by design.** Tooling exists and is locally verified; going live was explicitly held back this sprint for the user to decide, since it's a real, hard-to-reverse action with cost and security implications. |
| Ops dashboard live with real cost, latency, and health | **Met.** |
| Routing policy switchable live with both deltas visible | **Partially met.** The switching mechanism is real and meets F7.3's acceptance criterion. The dashboard's cost/accuracy dual-number display opens on a labelled fixture table because no `CostBreakdown` route exists yet and no frontier key is configured for real accuracy scoring — same root cause as Sprint 8's ablation gaps. |
| Public corpus is public-domain only, enforced in code and documented (ETH-1) | **Met.** A flagged upload gets a real 422 from the real HTTP route, not just an assertion on a helper function. |
| Uploads private, deletable, API-routing labelled (ETH-2, ETH-4) | **Met.** |
| Every screen responsive to 400px, keyboard-complete, ≥4.5:1 contrast | **Partially met, honestly scoped.** Real `axe-core` + jsdom pass across priority screens (review queue, graph explorer, both dashboard states, character detail, ask, landing, evals) found and fixed three real bugs. This is not a full live-browser/Lighthouse audit across every screen — no browser-automation tool was available this session. |
| 90-second recording cut; writeup published; README complete | **Not started.** Carried forward — see §4. |
| `traverse-prd.md` updated: §12 open decisions resolved, real numbers in §1.3 and Appendix A | **Not done this sprint.** Appendix A was last updated at Sprint 8's close; Sprint 9 didn't add new ablation cells. §12/§1.3 not yet touched. |
| Final `RETRO.md` — plus a project-level retrospective | This file is the sprint retro. A project-level retrospective across all nine sprints has not been written yet — carried forward. |

## 3. Real bugs found and fixed this sprint

1. **`api/query/pipeline.py::_finish`'s `greenlet_spawn` error** (be2) — flagged in Sprint 8, fixed for real. Three sequential commits on the same request-scoped session (`expire_on_commit=True`) expired a `Conversation` object mid-generator; a later synchronous attribute read couldn't refresh. Fixed by capturing the needed ids before the first commit.
2. **A real residency bypass** (be2): a live routing policy could previously route `answer`/`adjudicate` externally even under an explicit local-only setting — the residency floor only checked the `judge` purpose. Now applies to every purpose.
3. **No request timeout existed anywhere in `api/llm/**`** (be2, flagged by Sprint 8's do1, fixed for real) — 60s local / 120s frontier added to `api/llm/client.py`.
4. **A real pre-existing cross-project content-hash pooling bug** (be1): `create_book`'s idempotent-reingest fallback looked up content-hash matches globally, so a demo upload colliding with any existing book — even another private session's — was silently handed that book's id. Now scoped per-project; a genuine cross-project collision is a 409, never a silent reuse.
5. **`DELETE /books/{id}`'s naive ORM delete would have violated a `NOT NULL` constraint** (be1) — `session.delete()` tries to null `chapter.book_id` before Postgres's own cascade can run; caught by be1's own test, fixed with a raw `DELETE` statement.
6. **Two independently-built upload-management modules writing to the same table** (be1 + do1, reconciled in the fast-follow) — see §1's S9.5 row. Not a runtime bug that shipped, but exactly the kind of silent double-bookkeeping that becomes one under real concurrent load.
7. **Two real `tsc` compile errors slipped past fe1's own build verification** and were only caught at the merge train: `export type { X } from "..."` re-exports a name but doesn't bind it locally, so a file using that name in its own type annotations doesn't resolve; and an ambient `declare module "vitest" { interface Assertion ... }` conflicted with `@testing-library/jest-dom`'s own augmentation of the same interface under this project's installed versions, in a way that matching its type parameters exactly still didn't resolve — replaced with a helper function that casts at the one call site instead of touching global declaration merging at all.
8. **A dead Celery `beat_schedule` entry** (be1) — registered against a `celery beat` service that doesn't exist in `docker-compose.yml`, so it never actually ran; removed in favor of do1's real, invokable `make upload-sweep`.

## 4. What's carried forward — not because it slipped, but because it needs a human

This sprint deliberately stopped short of three things that are the user's call, not an agent's, and are still open:

1. **Actually going publicly live** (S9.4's remaining half). The tooling is built and locally verified. Someone needs to decide on a domain, a cloud host, and DNS, and accept the real cost/security exposure of a public URL. Exact steps are in `plans/sprint-9/HANDOFF.md`.
2. **The 90-second recording** (S9.14). This needs a live, screen-recorded walkthrough of the demo script — not something producible from inside this session without a recording tool and a decision on what "public" state to record against.
3. **The engineering writeup** (S9.15) and the **PRD's §12/§1.3 update** — both explicitly orchestrator-owned per the sprint's own scope table, not yet started.
4. **A project-level retrospective across all nine sprints** — the sprint's own DoD calls for this in addition to this file.

## 5. Process notes

- **Cross-story collisions on shared state are now a recurring, expected class of problem, not a one-off.** Sprint 8 had the ablation-runner/config-switch dependency; Sprint 9 had the upload-session/upload-guard collision. Both were caught at merge time (not before, since the agents genuinely couldn't see each other's finished code in either case) and both closed with a same-day fast-follow rather than blocking the whole sprint's close. This pattern is working — keep using it — but it argues for tighter story-level interface contracts at freeze time when two agents will plausibly touch the same table, not just the same migration.
- **An agent's own "all clean" build report is not sufficient evidence on its own.** fe1 reported `pnpm tsc --noEmit` clean, and it wasn't — two real compile errors were caught only because the orchestrator independently rebuilt and reran the test image rather than trusting the report. Worth keeping the practice of an independent merge-train verification pass per branch, even under time pressure to move fast.
- **Shared-host contention produced several transient failures this sprint** (db/rabbitmq containers recreated mid-test-run by concurrent peer sessions, one test flaking under load and passing clean in isolation) — consistent with prior sprints' experience, not a new problem, and correctly not chased as a code regression once reproduced clean in isolation.

# Sprint 7 — Human Review Queue

**Goal:** the pipeline pauses when it is unsure, a human answers in seconds, and
the correction cascades through the graph and never gets overwritten.

**PRD refs:** F5.1 – F5.4 · NFR-a11y

> PRD F3 on this feature: *"This is the differentiating feature. Build it
> properly."* Every competitor demo has a chatbot; almost none have a designed
> human-oversight loop. The eval numbers convert technical buyers, but this is
> what convinces them the builder has shipped production AI before.

The substrate already exists: the Postgres checkpointer was proven in Sprint 1,
merge/split cascade in Sprint 3, `resolve_conflict` rows in Sprint 4, and the
interrupt UI component in Sprint 6. This sprint connects them.

## Contract freeze (Day 1)

Migration `0012`: `review_task` finalised (`task_type`, `payload`,
`graph_thread_id`, `priority`, `status`, `resolution`), `correction_feedback`
(the store Sprint 8's calibration reads). `contracts/review.py`: the five task
payload types as a discriminated union.

## Scope

| Story | Owner | Summary | PRD |
|---|---|---|---|
| S7.1 | be2 | Ingestion as a LangGraph flow with real `interrupt()` points | F5.1 |
| S7.2 | be2 | Five task types with typed payloads and resolution handlers | F5.2 |
| S7.3 | be2 | Task priority — highest-leverage decisions first | F5.3 |
| S7.4 | be2 | Resume-on-resolve; restart-safety test under load | F5.1 |
| S7.5 | be1 | `human_verified` guards on every extraction write path | F5.4 |
| S7.6 | be1 | Re-run disagreement → new task, never silent overwrite | F5.4 |
| S7.7 | be1 | Correction feedback store for Sprint 8 calibration | F5.4 |
| S7.8 | fe1 | Review queue — keyboard-first, 50 tasks in under 8 minutes | F5.3 |
| S7.9 | fe1 | Five task renderers, each built for its decision | F5.2 |
| S7.10 | fe1 | Bulk accept for high-confidence groups | F5.3 |
| S7.11 | do1 | Review throughput metrics; task-age and queue-depth alerting | F7.4 |
| S7.12 | do1 | Chaos test: kill the worker mid-review, prove zero state loss | F5.1 |

**Priority ordering (S7.3) matters more than it looks.** A `merge_characters`
decision on a protagonist cascades through dozens of edges; a `confirm_relation`
on a minor pair does not. Order by blast radius, not by arrival.

## Demo script

1. Ingest *Wuthering Heights* → pipeline pauses at the two Catherines.
2. Review queue shows it **first**, above 40 lower-leverage tasks.
3. Side-by-side mention contexts with pages; reviewer chooses "keep separate".
4. Pipeline resumes; the graph rebuilds with two Catherines correctly separated.
5. Clear 50 tasks **without touching the mouse** — `j`/`k`/`a`/`e`/`m`, timed.
6. `docker compose kill celery-worker` mid-review → restart → queue and graph
   state intact, paused run resumes (F5.1's acceptance criterion).
7. Re-run extraction → every human decision preserved; one new model
   disagreement surfaces as a fresh task rather than overwriting (F5.4).

## Definition of Done

- [ ] 50 tasks cleared in under 8 minutes, keyboard only — **timed and recorded**
- [ ] Worker kill mid-review loses nothing
- [ ] Re-run preserves 100% of `human_verified` records
- [ ] Merge cascade leaves zero orphaned mentions or duplicate edges
- [ ] Every correction lands in the feedback store with enough context to
      calibrate on in Sprint 8
- [ ] `RETRO.md` written

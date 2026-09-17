# Sprint 7 · Backend Engineer 2

**Branch:** `ai/be2/sprint-7-review` · **Worktree:** `../traverse-wt/be2`
**Owned:** `api/graph/**`, `api/relations/**`, `api/query/**`, `api/review/**` (new),
`api/routes/review.py`

## Mission

Make the pipeline stop and ask. Everything needed exists — the checkpointer
proved out in Sprint 1, the conflict rows have been accumulating since Sprint 4.
Wire them into a flow that interrupts, persists, and resumes.

---

**S7.1 Ingestion as a LangGraph flow (F5.1).** The extraction stages currently
run as a Celery chain. Wrap the decision-bearing stages — alias resolution,
relation aggregation — in a LangGraph flow with the Postgres checkpointer, so an
ambiguity becomes an `interrupt()` rather than a coin flip.

Celery still owns the coarse pipeline and the long CPU/GPU stages. LangGraph owns
only the stages that can pause. Do not migrate parsing or embedding into
LangGraph — they have no decisions in them, and the checkpointer serialisation
cost on a 1,100-chunk payload is real.

Thread ID is the `book_id`, so a paused run is findable without a side table.

**S7.2 Task types (F5.2).** `merge_characters`, `confirm_relation`,
`resolve_conflict`, `classify_candidate`, `confirm_chapter_split`. Each payload
carries **everything the UI needs to decide without another round trip** —
contexts, quotes, pages, current confidence, and what the system would do
unattended.

Each resolution handler applies the decision (reusing Sprint 3's transactional
merge/split for `merge_characters`), writes `human_verified`, records to the
feedback store, and resumes the thread.

**S7.3 Priority.** Score by blast radius: how many edges and mentions the
decision affects, weighted by the importance tier of the characters involved.
A protagonist merge outranks 40 minor-pair confirmations, and a reviewer with 20
minutes should spend them where they matter.

**S7.4 Resume and restart safety (F5.1).** `POST /review/tasks/{id}/resolve`
resolves and resumes. Test the acceptance criterion literally: interrupt, kill
the process, restart, resume, complete — **under concurrent load**, because the
single-thread version already passed in Sprint 1 and the interesting failures
are contention failures.

Resolving an already-resolved task is idempotent, not an error — a double-click
must not corrupt a graph thread.

## DoD

- [ ] Interrupts fire at genuine ambiguity, not on a confidence threshold alone
- [ ] Five task types with self-sufficient payloads
- [ ] Priority ordering demonstrably surfaces the two Catherines first
- [ ] Restart-under-load test green
- [ ] `HANDOFF.md`: task payload union for fe1 — **Day 2**

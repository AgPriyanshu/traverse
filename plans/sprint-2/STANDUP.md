# Sprint 2 — Standup

## be2

**Landed:** S2.7 (`api/llm/` substrate — client/errors/routing/tracing/structured/budget,
old `api/llm.py` deleted), S2.8 (`plan_batches`, ahead of the Day-4 deadline),
S2.9 (hybrid retrieval, `GET /api/search` live), S2.10 (reranker behind
`RERANKER_ENABLED`, default off, measured not assumed). All four commits on
`ai/be2/sprint-2-ingestion`; nothing merged to `ai-master` yet.
**Next:** Idle unless the orchestrator wants S2 work merged early — my sprint
plan (`backend-2.md`) has nothing left in scope for Sprint 2.
**Blocked:** Not blocked. Filed SCR-2 (non-blocking) for
`settings.reranker_enabled`/`settings.reranker_model_id` — shipped S2.10
with a `getattr` default in the meantime, so nothing is waiting on it.

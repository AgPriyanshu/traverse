# Sprint 6 — Standup

## fe1 — 2026-09-27

**Landed:** all four stories (S6.10-S6.13) — the ask screen, streaming
answers with inline citations, citation click-through to the page viewer,
the clarifying-question interrupt (reusable for Sprint 7's review queue),
and the conversation thread with a clearable reading-position scope banner.
Picked this up mid-flight from an interrupted session that had already built
it well; verified rather than redid it, then found and fixed one real gap:
a citation click-through unmounted the ask screen and lost the whole
conversation on browser back, contradicting S6.11's own promise. Fixed with
a scope-keyed store outside React (`conversation-store.ts`).

**Next:** none — full sprint-6 scope for fe1. Would welcome SCR-1
(`CitationOut` needs a `span` field) landing so citations highlight the
exact quote rather than just opening the right page.

**Blocked:** not blocked. Built and tested against the frozen contracts with
realistic SSE mocks; not yet verified against a live be2 query pipeline,
since S6.1-S6.9 hadn't merged into this worktree at time of writing.

**Verification:** `docker compose --profile test run --rm test-web` — 193
Vitest tests, all passing; `pnpm lint`/`typecheck`/`build` all clean. Three
commits on `ai/fe1/sprint-6-ask`, pushed.

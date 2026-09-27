# Sprint 6 — Standup

## be1 — 2026-09-27

**Landed:** all three of be1's Sprint 6 stories — S6.7 name resolution
(`api/extraction/resolution.py::resolve_names`), S6.8 quote-span locator
(`api/pipeline/quotes.py::locate_quote`), S6.9 latency instrumentation
(`api/pipeline/timing.py::QueryTimer`). Picked this up from a prior session
that had already written all three modules, their tests, and the supporting
repository/render changes but left them uncommitted; verified the work
against the sprint spec and acceptance criteria (ambiguity surfaced not
guessed, `None` on an unlocated quote, TTFT measured at the API boundary),
fixed line-length lint (`ruff format`), committed in per-story chunks, and
ran verification. Signatures are in `HANDOFF.md`.

**Verification:** targeted run (resolution/quotes/timing/render/repository
tests, 48 cases) then the full suite — 489 passed, 1 pre-existing skip, no
regressions. `ruff check api` and `ruff format --check api` both clean.

**Next:** none — this was the full Sprint 6 scope for be1. Available for an
SCR if be2's S6.1-S6.6 integration surfaces a signature gap.

**Blocked:** not blocked.

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

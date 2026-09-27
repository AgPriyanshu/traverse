# Sprint 5 — Standup

## fe1 — 2026-09-27

**Landed:** all four stories (S5.9–S5.12) plus the routing refactor they
depend on — characters and the graph moved from `/books/:id/...` to
`/projects/:id/...` in one pass. Project screens (list, create, overview with
drag-to-reorder and an add-book form), the series roster (one row per
character, `<AppearanceStrip>`, "new in book N"), the series graph (client
book filter that animates, a server-side spoiler-safe reading-position
control, appearance-aware node size), and the relationship arc extended
across volumes with book-boundary ticks and per-transition book+page
citations, one code path for a 1-book or 3-book arc.

**Next:** none — this was the full sprint-5 scope for fe1. Would welcome
SCR-1/2 landing (`plans/sprint-5/SCR.md`) so the roster strip's mention
weighting and the multi-book mentions timeline can drop their client-side
workarounds.

**Blocked:** not blocked. Built and tested entirely against the frozen
contracts with realistic mocks (same pattern as Sprint 4's graph explorer);
not yet verified against a live be1/be2 backend, since neither had landed in
this worktree at time of writing.

# Sprint 8 — STANDUP

## fe1 — 2026-09-28

**Landed:** S8.6 (persistent reading-position slider — graph/characters/
character-detail/ask all scoped, `SeriesPositionControl` retired) and S8.7
(`/ops/evals` ablation table + calibration chart + metric trend, fixture-
backed). Both committed, both green (233 Vitest tests, `pnpm tsc --noEmit`,
`pnpm lint`, `pnpm build` clean).

**Next:** nothing further scoped for fe1 this sprint, but there's a real
follow-up once be2's S8.1 (`b796938`) merges to `ai-master` — it newly gates
`neighbourhood`/`relations/arc`/`relations/{id}/evidence`/`graph/path` on the
reading position, and the S8.6 slider doesn't send it to those four yet (the
evidence drawer and relation arc, specifically). Details and the exact hooks
to update are in `plans/sprint-8/HANDOFF.md`. Also watching do1's S8.8
ablation runner for a real `/ops/evals` route to swap the S8.7 fixtures for.

**Blocked:** nothing.

# Sprint 8 — Standup

## do1 — 2026-09-28

- **Landed:** S8.8 (ablation runner, cached/resumable, real extraction numbers
  for both gold books), S8.9 (regression gate, demonstrated failing on real
  data), S8.10 (README table auto-generated from the last run). SCR-1 filed
  for the resulting path-count bump.
- **Next:** nothing further planned this sprint unless be2's S8.2 lands and
  wants the config-switch hook wired in (see HANDOFF.md).
- **Blocked:** retrieval/model axis quality and variance measurement need a
  real `FRONTIER_API_KEY` (not provisioned) and be2's S8.2 (not landed as of
  this run) — both documented in `plans/sprint-8/HANDOFF.md`, neither is
  worked around or fabricated.

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

# Sprint 9 — fe1 HANDOFF

For be2 (S9.6 routing policy engine, S9.7 frontier API path) and do1 (cost
accounting) picking this up after fe1's stories land.

## S9.10 — Ops dashboard: exact swap points

The dashboard (`web/src/routes/ops/dashboard/`) is built against the frozen
contract shapes and already wired to every **live** route that exists today.
Two seams remain fixture-backed, both documented in code comments at the
point they're used, not just here:

1. **`GET`/`PUT /ops/routing-policy`** (`api/routes/ops.py`, currently
   `not_implemented(OWNER, "S9.6")`). `routing-control-panel.tsx` and
   `web/src/lib/inference-mode.ts`'s `useEffectivePolicy()` already call the
   real hooks (`useRoutingPolicy`/`useSetRoutingPolicy`, generated from the
   frozen `RoutingPolicyOut` contract) — the moment the handlers return real
   data instead of 501, **no frontend change is needed**. The panel already
   syncs its local edit state from a live response (`routing-control-
   panel.tsx`'s `syncedVersion` render-time check) and already calls the real
   `PUT` on "Apply to live traffic," reporting success or "preview only" off
   whatever the response actually is.

2. **`CostBreakdown`** (`api/contracts/api.py`) has no route at all yet. The
   routing panel's cost-per-query number and the 7-day trend chart
   (`fixtures.ts`'s `PURPOSE_UNIT_COST_USD`/`COST_TREND`) are a labelled
   placeholder unit-cost table, not a live meter. When a route exists (the
   natural shape: `GET /ops/cost-breakdown?window=` returning one
   `CostBreakdown`, or a list of them for the trend), swap:
   - `fixtures.ts`'s `costPerQueryFor` → a real per-purpose cost read off the
     latest `CostBreakdown.by_purpose`.
   - `fixtures.ts`'s `COST_TREND` → a `useQuery` over a windowed listing.
   - Delete `routes/ops/dashboard/types.ts`'s hand-mirrored `CostBreakdown`
     type once `pnpm gen:api` can generate `Schemas["CostBreakdown"]` (it
     can't today — FastAPI only emits a schema for a type a route
     references).

3. **Accuracy delta** already prefers a real `GET /ops/eval-runs/latest`
   result (built since S8.8) and only falls back to
   `fixtures.ts`'s `FALLBACK_MODEL_AXIS_RESULTS` on a 404 (no run recorded in
   this database yet). Nothing to swap here — just run `make eval-ablation`
   against a worktree's own database and the panel picks up real numbers on
   its own.

`web/src/lib/api/schema.d.ts` was regenerated against the shared integration
API mid-sprint (`API_URL=http://localhost:8000 pnpm gen:api`) — it now
includes `EvalRunOut`/`EvalResultOut`/`AblationConfig`/`MetricSet`/
`ReviewAlertsOut`/`QueryLatencyOut` as real generated types for the first
time. `routes/ops/evals/types.ts` (Sprint 8) still hand-mirrors its own copy
of the first four — that refactor was left for whoever next touches that
screen, per its own file-header note; the ops dashboard's new code (S9.10)
uses the generated ones directly and does not depend on `evals/types.ts`.

## S9.11 — SCR-1 (see `plans/sprint-9/SCR.md`)

`DoneEvent`/`RouteEvent` carry no field for which inference mode actually
served a given past answer — only the currently configured policy is
knowable client-side (`lib/inference-mode.ts`'s `useEffectivePolicy`). Not
blocking this sprint's DoD, but real: once S9.7's routed/fallback behavior
exists, "the policy says local" and "this particular answer happened to fall
back to frontier" can diverge, and today's UI can't tell the difference.
Proposed field and exact call sites to update are in the SCR.

## Testing

`jest-axe` + `axe-core` added as devDependencies (`web/package.json`,
`pnpm-lock.yaml` — installed and verified against
`pnpm install --frozen-lockfile`, which is what `docker-compose.yml`'s
`test-web` service runs). `web/tests/axe.ts` is the shared `runAxe` helper +
the Vitest `Assertion` type augmentation (jest-axe ships no Vitest-native
matcher). No CI config changes were needed or made — `test-web` already runs
`pnpm run test` (`vitest run`), which picks up every `.test.tsx` file
automatically, axe-based or not.

## Everything else

S9.10-13 are otherwise self-contained inside `web/src/**` — no other agent's
files were touched, and no other SCR/DCR was needed beyond SCR-1 above.

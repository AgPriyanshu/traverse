# Sprint 8 — fe1 HANDOFF

## S8.6 — the reading-position slider depends on be2's S8.1 wire shape

The persistent reading-position slider (`web/src/components/spoiler/`,
`ProjectLayout`) is built against **today's** `limit_book_order`/
`limit_chapter` shape: two independently optional `int | None` query params on
`GET /api/projects/{id}/graph`, `GET /api/projects/{id}/characters`,
`GET /api/characters/{id}`, `GET /api/characters/{id}/mentions`, and
`QueryRequest.limit_book_order`/`limit_chapter`.

As of this commit, `ai/be2/sprint-8-spoiler-calibration` had **not** touched
`api/contracts/api.py` or any `api/routes/*.py` — be2's `api/query/scope.py`
(`ReadingScope`, a frozen dataclass with `.unlimited()`) is an internal
refactor of the graph/query/retrieval layer's own function signatures, not a
wire-format change. The frontend sends exactly the same two query params it
always has.

**If S8.1 lands with a different wire shape** (e.g. a single combined
`reading_position` param, or promoting it to a required field with no
"omit for no limit" option), the frontend call sites to update are:

- `web/src/lib/api/hooks.ts` — `useProjectGraph`, `useCharacters`,
  `useCharacter`, `mentionsQueryOptions` all forward whatever `params` shape
  `openapi-typescript` generates from the live contract; `pnpm gen:api` picks
  up the new shape automatically once it's frozen and committed.
- Every call site currently doing `{ limit_book_order: position?.bookOrder ??
  undefined, limit_chapter: position?.chapter ?? undefined }` — `grep -rn
  "limit_book_order:" web/src` finds them all: `graph-explorer.tsx`,
  `characters.tsx`, `character-detail.tsx`, `project/ask.tsx`.
- `web/src/lib/reading-position.ts`'s `limitsForBook` (used by `book/ask.tsx`,
  which sits outside `<ProjectLayout>`'s reading-position context) — its
  return shape (`{ limitBookOrder, limitChapter }`) would need to match
  whatever the new params are called.

None of this touches the slider's own model (`SeriesPosition`,
`buildPositionSteps`, `localStorage`) — that's a pure frontend concept and is
shape-agnostic to how the API spells "the reading position" on the wire.

## For do1 (S8.8 — the ablation runner) and be2 (S8.2/S8.3)

`/ops/evals` (`web/src/routes/ops/evals/`) renders the ablation table,
calibration chart, and metric trend, built against the frozen
`EvalRunOut`/`EvalResultOut`/`AblationConfig`/`MetricSet`/
`CalibrationModelOut` contracts — but **there is no live route serving them
yet** as of this commit. `openapi-typescript` only generates a schema for a
type some route actually returns, so with no route, there's nothing to
generate; `web/src/routes/ops/evals/types.ts` hand-mirrors the five contract
classes field-for-field instead (comment at the top explains why this is an
exception to "never hand-write API types"), and `fixtures.ts` stands in with
three runs of realistic-looking, entirely invented numbers.

**When a real route lands**, the swap is contained to `evals-screen.tsx`'s
two imports — `EVAL_RUNS`/`LATEST_RUN` and `CALIBRATION` from `./fixtures` —
everything downstream (`AblationTable`, `CalibrationChart`,
`MetricTrendChart`, `MetricDrawer`, `ablation-config.ts`'s helpers) already
renders off the typed contract shape, not the fixture module. Once the route
exists, also delete `types.ts` and import the generated `Schemas["EvalRunOut"]`
etc. from `@/lib/api` instead (regenerate via `pnpm gen:api` first).

A few assumptions this screen makes that the real route should either match
or tell fe1 to change:

- **One `GET` returns (at least) the latest run**, `EvalRunOut`-shaped, with
  `results` populated — the table groups those by `axis` client-side.
  `EVAL_RUNS` (plural, sorted by `created_at`) feeds the trend chart; if the
  real API only ever returns the latest run, the trend chart needs a second
  endpoint or a `?history=` param rather than inventing one.
- **`EvalResultOut.book_key`** is rendered as a plain string label in the
  drill-down drawer — there's no contract link from it to a `Book`/`Project`
  id, so it isn't a citation or a clickable reference anywhere on this screen.
- **`CalibrationModelOut` is fetched/rendered as a separate concern**, not
  nested inside `EvalRunOut` — the contract doesn't nest it either, so this
  should already match, but flagging it in case the real route composes them
  together.
- **"Recommended" and "baseline" are derived structurally** from
  `AblationConfig`'s own fields (`ablation-config.ts`'s `isRecommended`/
  `isBaseline`), matching PRD Appendix A's named recommendation per axis —
  not read off any contract field, since there isn't one. If the runner adds
  an explicit `is_recommended`/`is_baseline` flag, prefer that over the
  structural guess.
- **No per-question breakdown** — `EvalResultOut` is one aggregate `MetricSet`
  per matrix cell, not a list of question-level results, so "drill into a
  cell" (frontend-1.md's brief) surfaces the full `MetricSet` (every field,
  including the ones the table's headline columns omit) rather than a
  per-question table. If a per-question contract lands, `metric-drawer.tsx`
  is where that list would go.

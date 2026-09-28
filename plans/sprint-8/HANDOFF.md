# Sprint 8 — fe1 HANDOFF

## S8.6 — checked be2's `ai/be2/sprint-8-spoiler-calibration` before finishing; one real follow-up

The persistent reading-position slider (`web/src/components/spoiler/`,
`ProjectLayout`) is built against `limit_book_order`/`limit_chapter`: two
independently optional `int | None` query params on
`GET /api/projects/{id}/graph`, `GET /api/projects/{id}/characters`,
`GET /api/characters/{id}`, `GET /api/characters/{id}/mentions`, and
`QueryRequest.limit_book_order`/`limit_chapter`.

**be2 landed S8.1 (`b796938`, "required ReadingScope enforces spoiler cutoff
everywhere") on their branch while this was being built.** Checked the actual
commit, not just the branch name: `ReadingScope` (`api/query/scope.py`) is
built at the route boundary from those exact same two query params
(`ReadingScope(book_order=limit_book_order, chapter=limit_chapter)`) — **the
wire shape is unchanged**, so nothing above needs updating once that branch
merges.

**What did change, and matters for fe1 the moment it merges to `ai-master`:**
`limit_book_order`/`limit_chapter` are now *also* accepted (and enforced) on
four endpoints that never had them before — `GET
/characters/{id}/neighbourhood`, `GET /relations/arc`, `GET
/relations/{id}/evidence`, and `GET /graph/path`. The frontend hooks for all
four (`useNeighbourhood`, `useRelationArc`, `useEvidence`, `useGraphPath` in
`web/src/lib/api/hooks.ts`) predate this and **do not send the reading
position** — `useEvidence` already forwards a generic `params` object
(nothing to change there beyond the call site), but `useNeighbourhood`/
`useRelationArc`/`useGraphPath` don't even accept params yet. Concretely,
`routes/project/graph/evidence-panel.tsx`/`evidence-item.tsx` (evidence
quotes — literal citations) and `relation-arc.tsx` (a pair's relationship
across chapters — literally "how did this change over time") are surfaces
the S8.6 brief's "nothing from chapter 6+ present as node, edge, or citation"
covers and this build did not close, because the server had nowhere to
enforce it until this commit.

**Action once be2 merges:** rebase, `pnpm gen:api` (schema.d.ts doesn't have
these four endpoints' new params yet — checked, they're absent as of this
writing), then thread `limit_book_order`/`limit_chapter` from
`useReadingPositionContext()` through `useEvidence`'s existing `params`, and
add a `params` argument to `useNeighbourhood`/`useRelationArc`/`useGraphPath`
the same way `useCharacter` already does it, then pass them from
`evidence-panel.tsx` and `relation-arc.tsx`. Not done in this sprint's
S8.6 commit because the backend enforcement didn't exist yet when that work
started and landed mid-sprint — flagging rather than guessing at an unmerged
branch's contract.

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

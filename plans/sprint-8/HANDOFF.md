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

## S8.7 — see the section below (added once the screen landed)

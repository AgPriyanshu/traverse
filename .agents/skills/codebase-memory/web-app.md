# Web app

React 19 · TypeScript · Vite 8 · Chakra UI v3 · react-router v8 ·
TanStack Query v5 · pnpm. Symbols over line numbers.

## Current state

**Built (S1):** app shell, the full S1–S9 route table, the typed API client,
every read/write hook for the frozen contract, the S1 primitives, and the
library/upload/ingestion-shell screens. 99 Vitest tests
(`web/tests/*.test.{ts,tsx}`), all passing; `pnpm tsc --noEmit`, `pnpm lint`,
`pnpm build` all clean.

`web/src/design-system/tokens.ts` **exists** (DCR-1, landed at the Sprint 2
freeze) — `palette`, `shadow`, `type`, `space`, `radius`, `motion`. `theme.ts`
imports `{ palette, shadow }` from it; shadows are now real `semanticTokens`
with distinct light/dark values (they were a single static value before,
DCR-3). Light `relation.social` was darkened `#8A6A12` → `#7F6210` to clear
4.5:1 on `sunken` (DCR-2). A missing token is still a DCR, never a local
addition — `tokens.ts` stays orchestrator-owned.

## Structure

```
src/
  app.tsx                    QueryClientProvider + RouterProvider. No DesignSystemProvider
                              here — main.tsx owns it, outside the query client.
  main.tsx                   DesignSystemProvider(App)
  design-system/
    theme.ts                 palette + Chakra system config. `export const palette`
                              is the DCR-1 stopgap — see above.
    provider.tsx              ThemeProvider (next-themes, class strategy, system default)
                              wrapping ChakraProvider.
    use-color-mode.ts         useColorMode() — resolvedTheme, toggleColorMode.
  lib/
    use-hydrated.ts           useHydrated() via useSyncExternalStore — for anything
                              (the theme toggle) that must not announce a mode before
                              the client resolves one.
    format/index.ts           formatPageRange, pageRefLabel (the a11y name — always
                              "page N of Title"), formatChapterLabel, formatDuration,
                              formatRelativeTime, formatCount, formatBytes,
                              formatAliasRun. Tested in tests/format.test.ts.
    api/
      schema.d.ts             generated — `pnpm gen:api`. Do not hand-edit.
      client.ts                openapi-fetch instance. `API_BASE_URL` resolves to
                              `window.location.origin` (never a literal host — a
                              relative "" cannot be parsed by fetch outside a
                              browser, e.g. in Vitest). `fetch` is dereferenced from
                              globalThis per call, not captured at module load, so
                              tests can stub it.
      errors.ts                ApiError (status/detail from FastAPI's `{detail}` or
                              the 422 `[{loc,msg}]` list), NetworkError (fetch never
                              landed), describeError/titleForError — a 501 renders
                              as "Not built yet", not "Something went wrong".
      types.ts                 Re-exports of components["schemas"] under short
                              names (Book, Character, Graph, QueryEvent, ...),
                              STAGE_ORDER/STAGE_LABELS (the 9 frozen stages, display
                              order), isTerminalStatus (ready|failed).
      query-keys.ts             One factory object — every hook's queryKey comes
                              from here so invalidation can't miss a differently
                              spelled key.
      query-client.ts           createQueryClient() — no retry on 4xx/501.
      hooks.ts                  One TanStack hook per contract endpoint. Notable:
                              `useLibrary()` fans out `useProjects` + `useQueries`
                              over `GET /projects/{id}` because there is no flat
                              book list yet (SCR-1) — collapses to one call with no
                              screen change when that lands. `useBookStatus` polls
                              at 2s and returns `false` on a terminal status or a
                              query error. `useUploadBook` hand-serialises the
                              multipart body because the contract types the file
                              part as `string`.
  components/
    ui/                        Chakra-composed primitives, all in the barrel
                              `components/ui/index.ts`.
      page-ref.tsx              <PageRef> — see below.
      async-boundary.tsx         <AsyncBoundary> = Suspense + a class ErrorBoundary
                              wired to QueryErrorResetBoundary, so retry also clears
                              the failed query.
      empty-state.tsx, error-state.tsx, loading-skeleton.tsx, not-yet-built.tsx
      status-dot.tsx / status-tone.ts   dot-and-word status (never a pill); tone
                              helpers split into their own file so
                              react/only-export-components stays quiet.
      icons.tsx                 Hand-drawn inline SVGs. **Chakra v3's `<Icon>`
                              defaults to `asChild`** — pass a real `<svg>`-owning
                              child or it drops children into the tree with no
                              wrapper and React warns "the tag <path> is
                              unrecognized". `Glyph` here sets `asChild={false}`.
      color-mode-toggle.tsx      Uses useHydrated to avoid announcing a mode before
                              the client resolves one.
    layout/                    app-shell, top-bar, side-nav, page-header, nav-links,
                              nav-items (route tables for the nav), health-indicator
                              (polls `/api/health` every 30s), skip-link (first in
                              the tab order, visible on focus).
  routes/
    routes.tsx                 The `RouteObject[]` — the whole S1–S9 surface,
                              `<NotYetBuilt screen sprint>` for anything unbuilt.
                              Kept apart from router.tsx so tests can mount it in a
                              `createMemoryRouter` without touching the browser one.
    router.tsx                  createBrowserRouter(routes) — the real app import.
    not-found.tsx, route-error.tsx
    books/library.tsx, books/book-card.tsx
    books/upload.tsx, books/validate-upload.ts   PDF-only, 200MB cap client-side.
    book/book-layout.tsx        tab nav + header for `/books/:bookId/*`.
    book/overview.tsx, book/stage-stepper.tsx    always renders all 9 STAGE_ORDER
                              entries; one the backend hasn't reported yet shows
                              pending rather than vanishing (PRD F1.1).
```

## Routes

Declared in full at S1 with `<NotYetBuilt/>` placeholders — adding a route later
is a refactor, stubbing it now is a one-line swap. Table lives in
`src/routes/routes.tsx`; tested exhaustively in `tests/routes.test.tsx`.

Routes move to **project scope** in S5; `/books/:id/...` survives only for
book-local views (pages, chapters).

| Route | Screen | Sprint |
| --- | --- | --- |
| `/` | redirect to `/books` | Built |
| `/books` | library (real data via `useLibrary`) | Built |
| `/books/upload` | upload — drag/drop, PDF+200MB validation, real 501 error surface | Built |
| `/books/:id` | ingestion progress stepper (shell; polls `useBookStatus`) | Built |
| `/books/:id/chapters` | chapters + chunk inspector | S2 |
| `/books/:id/pages/:n` | page viewer | S2 |
| `/books/:id/characters` | roster | S3 |
| `/books/:id/characters/:cid` | character detail | S3 |
| `/books/:id/graph` | graph explorer | S4 |
| `/books/:id/ask` | Q&A with citations | S6 |
| `/books/:id/review` | review queue | S7 |
| `/projects` | project list | S5 |
| `/projects/new` | create project (standalone \| series) | S5 |
| `/projects/:id` | books in series order, drag to reorder, add book | S5 |
| `/projects/:id/characters` | series roster + appearance strip | S5 |
| `/projects/:id/graph` | series graph, book filter | S5 |
| `/projects/:id/ask` | Q&A with citations | S6 |
| `/ops`, `/ops/evals` | dashboard, ablations | S8/S9 |

## Key components

| Component | Note | Sprint |
| --- | --- | --- |
| `<AsyncBoundary>`, `<EmptyState>`, `<ErrorState>`, `<LoadingSkeleton>`, `<NotYetBuilt>` | Built. | S1 |
| `<PageRef page={n}>` | Built. Typographic cross-reference — oldstyle figures under a hairline dotted rule, no chip. A link (`react-router` `<Link>`) whose accessible name is always `pageRefLabel()` ("page 214 of Pride and Prejudice"); degrades to a plain `<Span>` when `bookId` is absent or `unavailable` is set. | S1 |
| `<StageStepper>` | Built. Renders all 9 `STAGE_ORDER` entries always, in order. | S1/S2 |
| `<PageViewer>` | pdfjs-dist; `highlights` prop in the PDF coordinate space agreed with be1 in S2. Deep-linkable. | S2 |
| `<EvidenceItem>` | quote + page ref + assertion badge; `hearsay` must read differently at a glance | S4 |
| `<RelationArc>` | temporal sequence; a 1-state arc renders through the same path as a 3-state one, and a 3-book arc through the same path as a 1-book one | S4, S5 |
| `<AppearanceStrip>` | per-book presence band; needs a text equivalent — a coloured band alone is not an answer | S5 |
| Graph explorer | Cytoscape.js + `fcose`. Layout cached — recomputing on every filter makes it jump. **List view is an equal, not a stub.** | S4 |
| Review queue | `j/k/a/e/m/s/x/u`. Prefetch next 3; optimistic with undo. Target: 50 tasks in <8 min, no mouse. | S7 |

## Gotchas

- **Never hand-write API types.** `pnpm gen:api` regenerates
  `src/lib/api/schema.d.ts` from `/openapi.json` (defaults to `:8000`, override
  with `API_URL`); it is committed and `pnpm gen:api:check` fails on drift.
- SSE event unions have explicit discriminators (`QueryEventEnvelope.event`,
  `oneOf` + `discriminator`) but **each event's `type` field is a `const` with a
  `default=`**, which FastAPI emits as optional — `openapi-typescript` types it
  `type?: "token"` rather than `type: "token"` (SCR-2). A `switch` still
  narrows correctly; an exhaustiveness check does not prove `type` present.
- The frozen API has **no CORS middleware** (SCR-3) — the browser cannot call
  it cross-origin. `vite.config.ts` proxies `/api` and `/health` to
  `VITE_API_BASE_URL` in dev; the container must do the same with nginx. The
  client always requests same-origin (`API_BASE_URL = window.location.origin`).
- The contract has **no flat book list** (SCR-1) — only `ProjectDetailOut.books`.
  `useLibrary()` is the one hook that fans out; every screen should read
  through it rather than re-deriving books from `useProjects` + N detail calls.
- Chakra v3's `<Icon>` defaults to `asChild` — see `components/ui/icons.tsx`.
- URL search params hold filters, selected entity, page, and the spoiler chapter
  limit — citations are links and must survive a reload. Not yet exercised;
  no screen in S1 has filter state.
- `localStorage` only for per-viewer conveniences (theme, reader's chapter
  position). Wrap in try/catch; it throws in private windows. `next-themes`
  already does this internally for the theme.
- Polling `refetchInterval` must return `false` on terminal states **and** on
  a query error — see `useBookStatus`.
- **Design tokens are frozen** (`design-system/tokens.ts`, orchestrator-owned)
  but do not exist yet — see DCR-1 above and
  [design/DESIGN.md](../../../design/DESIGN.md). `theme.ts`'s `palette` export
  is a documented stopgap, not a precedent for adding tokens elsewhere.
- The palette is contrast-checked in `tests/contrast.test.ts` (WCAG 2.x
  relative luminance, 4.5:1, both themes, `paper`/`surface`/`sunken`) —
  extend this rather than eyeballing a new colour. Light `relation.social` is
  a known exception below the floor on `sunken` (DCR-2); no screen uses
  relation colours until S4.
- Colour is never the only channel — relation families carry a line style too
  (not yet exercised; first consumer is S4's graph explorer).
- Every screen works at 400px — enforced by layout choices (`Wrap`, `hideFrom`/
  `hideBelow`, no fixed widths wider than `sidenav`), not by `overflow-x:
  hidden` (removed — it would mask a real overflow bug rather than surface
  one). `axe` runs in CI from S9.

## Related

[web/AGENTS.md](../../../web/AGENTS.md) · [.agents/rules/web.md](../../rules/web.md) ·
[design/DESIGN.md](../../../design/DESIGN.md) · [query-path.md](query-path.md) ·
[plans/sprint-1/SCR.md](../../../plans/sprint-1/SCR.md) ·
[plans/sprint-1/HANDOFF.md](../../../plans/sprint-1/HANDOFF.md)

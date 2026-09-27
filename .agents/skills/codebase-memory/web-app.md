# Web app

React 19 · TypeScript · Vite 8 · Chakra UI v3 · react-router v8 ·
TanStack Query v5 · pnpm. Symbols over line numbers.

## Current state

**Built (S1):** app shell, the full S1–S9 route table, the typed API client,
every read/write hook for the frozen contract, the S1 primitives, and the
library/upload/ingestion-shell screens.

**Built (S2, fe1):** real upload progress + already-ingested/retry handling
(S2.11), an app-wide toaster primitive, live ingestion progress with
retry-from-stage and a local ETA fallback (S2.12), the chapters list + chunk
inspector drawer (S2.13), and the page viewer — zoom, nav, keyboard, a
percentage-based highlight API, deep-linkable (S2.14). 128 Vitest tests
(`web/tests/*.test.{ts,tsx}`), all passing; `pnpm tsc --noEmit`, `pnpm lint`,
`pnpm build` all clean.

**Built (S3, fe1):** the character roster (S3.10, `/books/:id/characters`) —
tier-grouped (protagonists first), alias-aware client-side search, tier
filter, sort by mentions/first-appearance/name, all as URL search params.
Character detail (S3.11, `/books/:id/characters/:characterId`) — header with
tier badge and chapter span, an aliases card built from `alias_detail`
(surface form, count, `resolution_method` in plain English), a cited
attributes card, an interactive per-chapter mentions timeline
(`mentions-timeline.tsx` — click a bar to filter the mention list, synced via
the `?chapter=` search param), a paginated mention list, and an empty
Relationships panel placeholder for S4. The alias/mention inspector drawer
(S3.12, `mention-inspector-drawer.tsx`) audits every mention grouped by
surface form with `resolution_method` shown per mention as the trust
affordance the brief asks for. 136 Vitest tests, all passing; `pnpm
tsc --noEmit`, `pnpm lint`, `pnpm build` all clean.

**Built (S4, fe1):** graph explorer (moved to `routes/project/graph/` in S5 — see below): `graph-explorer.tsx` (route, URL-param filters via `graph-filters.ts`), `graph-canvas.tsx` (Cytoscape + fcose, layout computed once, filters hide in place), `graph-list-view.tsx` (the accessible equal), `evidence-panel.tsx` + `evidence-item.tsx` (drawer, `?edge=`), `relation-arc.tsx` + `arc-segments.ts`, `character-relationships.tsx` (detail-page panel). Family colour + line style live in `relation-style.ts`. The roster sparkline now reads `CharacterOut.mentions_per_chapter`. See `plans/sprint-4/SCR.md` SCR-10 to 12 and DCR-5 for known gaps.

**Built (S5, fe1):** the routing refactor — characters and the graph moved
from `/books/:id/...` to `/projects/:id/...` in one pass; `/books/:id/...`
now holds only book-local views (overview, chapters, pages, ask, review).
Project screens (`routes/project/`): `project-list.tsx` (`/projects`),
`project-new.tsx` (`/projects/new`, standalone/series both create a
`ProjectOut` — a standalone is a one-book project, no second code path),
`project-overview.tsx` (`/projects/:id` — books in series order, drag-to-
reorder via native DnD with an up/down-button keyboard equivalent
(`reorder-books.ts`), a "recomputing" banner while the reorder mutation and
its cache invalidation are in flight, `add-book-form.tsx` prefilling
`series_order` to the next open slot), and `project-layout.tsx` (the tab nav
shared by every project screen, the series-wide equivalent of
`<BookLayout>`). The series roster (S5.10, `characters.tsx` +
`character-row.tsx`) is one row per character with `<AppearanceStrip>`
(`appearance-strip.tsx` — a per-book presence band with an always-visible
text caption, never colour alone) and a "new in book N" filter alongside the
existing tier/search/sort ones. Character detail
(`project/character-detail.tsx`) gained an Appearances section (per-book
first page, tier, mention count, surface forms, each linking into that book)
and a book selector for its mentions timeline (see the SCR-2 gotcha below).
The graph explorer (`project/graph/`) fetches the **whole standing graph**
once and adds a client-side book filter (`GraphFilters.bookFilter`,
`graph-filters.ts`) that reuses S4's "layout once, animate the filter"
mechanism — the same one family/tier/confidence already used — plus a
server-side, spoiler-safe series-position control
(`series-position-control.tsx`, `limit_book_order`/`limit_chapter` query
params) that is a hard re-fetch, not an animated slice. Node size is now
appearance-aware (`nodeSize()` in `graph-canvas.tsx`, tier base size plus a
step per extra book appeared in) and a dashed ring marks "first appears in
this book" when a book filter is active. `<RelationArc>`
(`project/graph/relation-arc.tsx`, `arc-segments.ts`) now lays every book's
chapters end to end on one axis (`buildBoundaries`) so a pair's arc spans
volumes with book-boundary tick marks and a per-transition book+page
citation; a standalone's one-book case runs through the identical code path
with `boundaries.length === 1`. `edgeChapterSpan`'s single-book chapter join
was replaced everywhere by `edgeBookOrders` (page refs already carry
`book_order`, no per-book chapter fetch needed at the graph-list level — the
exact chapter still surfaces one level down, in the evidence panel and the
arc). 180 Vitest tests, all passing; `pnpm typecheck`, `pnpm lint`, `pnpm
build` all clean. See `plans/sprint-5/SCR.md` SCR-1/2 for the two carried
gaps and DCR-1 for the missing design artboards this sprint had to
extrapolate from.

**Known gap:** `MentionOut` and `EvidenceOut` carry a page but no `SpanBox`, so their click-through lands on the page without a highlight (Sprint 3 SCR-9, Sprint 4 SCR-10). The roster sparkline gap (Sprint 3 SCR-1) is closed for the single-book roster; its series-roster descendant reopens a version of it (Sprint 5 SCR-1 — see above).

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
                              at 2s, backs off to 10s after 5 minutes (a ref tracks
                              poll start per bookId), and returns `false` on a
                              terminal status or a query error. `useUploadBook`
                              hand-serialises the multipart body because the
                              contract types the file part as `string`, and its
                              result can be `AlreadyIngestedOut` (SCR-10, not yet
                              in the generated contract) — narrow with
                              `isAlreadyIngested`. `chunksQueryOptions` and
                              `pageRenderQueryOptions` are `queryOptions`-shaped
                              factories (not hooks) — `useChunks`/`usePageRender`
                              spread them, and so does anything that needs the
                              *same* query manually: the chunk inspector's
                              `useQueries` pagination and the page viewer's
                              neighbour (±1) `prefetchQuery`.
      upload.ts                 `uploadMultipart` — goes around `openapi-fetch`
                              to use `XMLHttpRequest.upload.onprogress` directly;
                              `fetch` cannot report upload progress at all.
  lib/ingestion-eta.ts          `estimateSecondsRemaining` — a local fallback ETA
                              from completed stage durations × remaining stage
                              count, used until the backend populates
                              `estimated_seconds_remaining` itself.
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
                              Imported directly (`@/components/ui/icons`), not
                              through the barrel.
      color-mode-toggle.tsx      Uses useHydrated to avoid announcing a mode before
                              the client resolves one.
      toaster.tsx / toaster-instance.tsx   `<AppToaster>` (mounted once in
                              `app.tsx`) + the `toaster` singleton anything can call
                              (`toaster.create(...)`) — e.g. the "already
                              ingested, opening the existing book" redirect toast.
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
                              pending rather than vanishing (PRD F1.1). Failed
                              stage gets a **Retry from this stage** button
                              (`POST /reprocess?from_stage=`).
    book/chapters.tsx, book/chunk-inspector.tsx   chapters list + a drawer (not a
                              route) for its chunks. The chunks endpoint has no
                              `chapter_id` filter (plans/sprint-2/SCR.md SCR-2) —
                              the drawer pages through the book's chunks (500 at a
                              time) and filters client-side by `chapter_id`,
                              stopping once it has `chapter.chunk_count` matches.
    book/page.tsx, book/page-viewer.tsx   the route wrapper (parses `:page` and
                              `?highlight=`) and the reusable `<PageViewer>` — see
                              below.
  project/                    S5: characters, graph and project screens all
                              moved here from `book/`, project-scoped now that
                              a book can be one of several volumes.
    project-list.tsx, project-new.tsx, project-overview.tsx, project-layout.tsx,
    add-book-form.tsx, reorder-books.ts, project-lookup.ts   S5.9 project
                              screens. `project-overview.tsx` drags books to
                              reorder (native HTML5 DnD) with an up/down-button
                              keyboard equivalent (`reorder-books.ts`'s
                              `moveBook`/`moveBefore`), shows a "recomputing"
                              banner while `useReorderBooks`'s mutation and its
                              follow-on cache invalidation are in flight, and
                              `add-book-form.tsx` prefills `series_order` to
                              `nextSeriesOrder()` — editable, since books may
                              arrive out of order. `project-layout.tsx` is the
                              tab nav shared by every project screen, the
                              series-wide equivalent of `<BookLayout>`.
    characters.tsx (was book/characters.tsx)   the series roster (S3.10, moved
                              and extended S5.10). Fetches the project's full
                              character list once (`useCharacters(projectId)`,
                              no `book_id` filter — the roster is series-wide)
                              and does search/tier/"new in book N"/sort
                              client-side. Filter/sort state lives in
                              `?q=&tier=&new=&sort=`.
    character-row.tsx (was book/character-row.tsx)   one roster row — one per
                              character, never one per book. Aliases render as
                              the italic serif run `formatAliasRun` (design/
                              DESIGN.md §2). Carries an `<AppearanceStrip>` in
                              place of S3's per-chapter sparkline, and a "new
                              in bk. N" mark for a single-appearance character.
    appearance-strip.tsx        `<AppearanceStrip>` (S5.10). A per-book
                              presence band — filled slots, `isFirst` ring,
                              optional `intensity` (0–1, real weight when the
                              caller has it, uniform when it doesn't — see the
                              SCR-1 gotcha below). Always prints a visible text
                              caption ("books 1–3") beside the band; a coloured
                              band alone is not an answer.
    character-tier-badge.tsx, character-labels.ts (was book/*)   `TIER_ORDER`,
                              `TIER_LABEL`, `RESOLUTION_METHOD_LABEL` (e.g.
                              `nickname` → "nickname table") — the plain-English
                              strings the S3.12 trust affordance depends on.
    character-detail.tsx (was book/character-detail.tsx)   S3.11, extended
                              S5.10. Header, an aliases card off
                              `CharacterDetailOut.alias_detail`, a cited
                              attributes card, an Appearances section (new —
                              per-book first page/tier/mention count/surface
                              forms from `CharacterDetailOut.appearances`, each
                              linking into that book), a book-scoped
                              `<MentionsTimeline>` with a book selector (see
                              the SCR-2 gotcha), a paginated mention list
                              (`use-paged-mentions.ts`), and the Relationships
                              panel (`graph/character-relationships.tsx`).
    mentions-timeline.tsx, sparkline-bars.tsx (was book/*)   the interactive
                              per-chapter bar chart (dataviz skill followed —
                              single-hue magnitude series, no legend needed,
                              selection carries a visible ring so colour is
                              never the only channel) and the presentational
                              SVG bar renderer it and the roster row's mini
                              sparkline both share.
    chapter-lookup.ts (was book/chapter-lookup.ts)   `chapterForPage`/
                              `chapterKeyForPage` — buckets a `MentionOut.page`
                              into a chapter via one book's own
                              `Chapter.page_start`/`page_end` ranges. Since S5
                              it is always called with the *selected* book's
                              own chapters (never a cross-book chapter list),
                              precisely to avoid the chapter-number collision
                              SCR-2 describes.
    use-paged-mentions.ts (was book/use-paged-mentions.ts)  incremental
                              pagination over `GET /characters/{id}/mentions`,
                              same shape as `chunk-inspector.tsx`'s manual
                              `useQueries` pagination — a character can carry
                              1,000+ mentions. Shared by the detail page's
                              mention list and the drawer below.
    mention-inspector-drawer.tsx (was book/mention-inspector-drawer.tsx)
                              S3.12. Every mention grouped by surface form
                              (from `alias_detail`), each group expandable to
                              its individual mentions — `resolution_method`
                              shown per mention, not just per group. Takes
                              `books: readonly Book[]` now (not a single
                              `bookId`/`bookTitle`) and resolves each mention's
                              citation off its own `mention.book_id`.
    graph/ (was book/graph/)    S4, project-scoped and extended S5.11/S5.12.
                              `graph-explorer.tsx` fetches the whole standing
                              graph once (`useProjectGraph(projectId, {
                              limit_book_order, limit_chapter })` — no
                              `book_id` server param) and layers a
                              client-side book filter
                              (`graph-filters.ts`'s `GraphFilters.bookFilter`,
                              `edgeBookOrders`) through the same "layout once,
                              animate the filter" mechanism `graph-canvas.tsx`
                              already used for family/tier/confidence — the
                              book filter is a *slice* of one graph, not a
                              fresh fetch. `series-position-control.tsx` is
                              the spoiler gate: picking `(book, chapter)` sets
                              `limit_book_order`/`limit_chapter`, a hard
                              server-side re-fetch, never a client filter.
                              `graph-canvas.tsx`'s `nodeSize()` is now
                              appearance-aware (tier base size plus a step per
                              extra book appeared in, capped), and a dashed
                              `.first-in-book` ring marks a node whose
                              `first_book_order` matches the active book
                              filter. `relation-arc.tsx` + `arc-segments.ts`
                              lay every book's chapters end to end on one axis
                              (`buildBoundaries`) so a pair's arc spans volumes
                              with book-boundary ticks and a per-transition
                              book+page citation (`citationFor` picks the page
                              ref in the state's own first book); a
                              standalone's one-book case is
                              `boundaries.length === 1`, the same code path.
                              `graph-list-view.tsx`/`character-relationships.tsx`
                              cite "bk. 1–2" (`edgeBookOrders` +
                              `formatSeriesOrderRun`) rather than a chapter
                              span — the exact chapter is one click away, in
                              the evidence panel and the arc, both of which
                              already carry it per item.
```

## Routes

Declared in full at S1 with `<NotYetBuilt/>` placeholders — adding a route later
is a refactor, stubbing it now is a one-line swap. Table lives in
`src/routes/routes.tsx`; tested exhaustively in `tests/routes.test.tsx`.

Routes moved to **project scope** in S5 — `/books/:id/...` now holds only
book-local views (overview, chapters, pages, ask, review). Characters and the
graph, previously book-scoped (S3/S4), moved to `/projects/:id/...` in the
same pass, since a book can be one of several volumes reconciled into one
project roster.

| Route | Screen | Sprint |
| --- | --- | --- |
| `/` | redirect to `/books` | Built |
| `/books` | library (real data via `useLibrary`) | Built |
| `/books/upload` | upload — drag/drop, PDF+200MB validation, real 501 error surface | Built |
| `/books/:id` | ingestion progress stepper, retry-from-stage, local ETA | Built |
| `/books/:id/chapters` | chapters + chunk inspector | Built |
| `/books/:id/pages/:n` | page viewer | Built |
| `/books/:id/ask` | Q&A with citations | S6 |
| `/books/:id/review` | review queue | S7 |
| `/projects` | project list — name, kind, book/character/relation counts | Built (S5) |
| `/projects/new` | create project (standalone \| series) | Built (S5) |
| `/projects/:id` | books in series order, drag to reorder, add book | Built (S5) |
| `/projects/:id/characters` | series roster + appearance strip (moved from `/books/:id/characters`, S3.10) | Built (S5) |
| `/projects/:id/characters/:cid` | character detail + appearances section (moved from `/books/:id/...`, S3.11) | Built (S5) |
| `/projects/:id/graph` | series graph, book filter, series-position control (moved from `/books/:id/graph`, S4) | Built (S5) |
| `/projects/:id/ask` | Q&A with citations | S6 |
| `/ops`, `/ops/evals` | dashboard, ablations | S8/S9 |

## Key components

| Component | Note | Sprint |
| --- | --- | --- |
| `<AsyncBoundary>`, `<EmptyState>`, `<ErrorState>`, `<LoadingSkeleton>`, `<NotYetBuilt>` | Built. | S1 |
| `<PageRef page={n}>` | Built. Typographic cross-reference — oldstyle figures under a hairline dotted rule, no chip. A link (`react-router` `<Link>`) whose accessible name is always `pageRefLabel()` ("page 214 of Pride and Prejudice"); degrades to a plain `<Span>` when `bookId` is absent or `unavailable` is set. | S1 |
| `<StageStepper>` | Built. Renders all 9 `STAGE_ORDER` entries always, in order. | S1/S2 |
| `<PageViewer>` | Built (`routes/book/page-viewer.tsx`). Renders the backend's already-rendered PNG directly (no `pdfjs-dist` — the contract gives a raster `image_url`, not a PDF to parse client-side). `highlights` are positioned as a plain percentage of `PageRenderOut.width`/`.height` (`left = x/width`, …) over a box sized to the image's actual rendered box at the current zoom — no DPI/scale math, correct at every zoom level for free *if* `width`/`height` share `SpanBox`'s coordinate space. That's flagged for be1 to confirm, not yet proven (`plans/sprint-2/HANDOFF.md`). Deep-linkable via `?highlight=x,y,w,h` (`routes/book/page.tsx` parses it). | S2 |
| `<EvidenceItem>` | quote + page ref + assertion badge; `hearsay` must read differently at a glance | S4 |
| `<RelationArc>` | temporal sequence; a 1-state arc renders through the same path as a 3-state one, and a 3-book arc through the same path as a 1-book one | S4, S5 |
| `<AppearanceStrip>` | Built (`routes/project/appearance-strip.tsx`). Per-book presence band with an always-visible text caption ("books 1–3") — a coloured band alone is not an answer. `intensity` is uniform on the roster row (SCR-1 gap), real on the character detail page. | S5 |
| Graph explorer | Cytoscape.js + `fcose`, project-scoped since S5 (`routes/project/graph/`). Layout cached — recomputing on every filter makes it jump; the S5.11 book filter reuses this, so it animates too. **List view is an equal, not a stub.** | S4, S5 |
| `<SeriesPositionControl>` | Built (`routes/project/graph/series-position-control.tsx`). The spoiler gate — picking `(book, chapter)` always pins a real chapter (defaults to that book's last), never a book with an undefined one. A hard server re-fetch (`limit_book_order`/`limit_chapter`), not a client filter. | S5 |
| Review queue | `j/k/a/e/m/s/x/u`. Prefetch next 3; optimistic with undo. Target: 50 tasks in <8 min, no mouse. | S7 |
| `<CharacterTierBadge>` | Built (`routes/project/character-tier-badge.tsx`). Accent treatment only for `protagonist`; every other tier is a neutral `bg.sunken`/`fg.muted` badge — there is no per-tier token, and one was not invented for this. | S3 |
| `<SparklineBars>` | Built (`routes/project/sparkline-bars.tsx`). A single-hue magnitude bar chart, `interactive` (keyboard-operable `rect`s, click-to-select, a stroke ring on the selected bar) or not (the roster row's mini chart). `responsive` stretches to its container at a fixed height via `viewBox` + `preserveAspectRatio="none"`. | S3 |
| `<MentionsTimeline>` | Built (`routes/project/mentions-timeline.tsx`). Wraps `<SparklineBars>` with a client-derived per-book histogram (S5 — see the SCR-2 gotcha; no longer trusts the aggregate `mentions_per_chapter` directly) → sorted points and a handful of evenly-spaced axis labels, never one per chapter. | S3, S5 |
| `<MentionInspectorDrawer>` | Built (`routes/project/mention-inspector-drawer.tsx`). Groups mentions by surface form off `alias_detail`; `resolution_method` shown per mention as the trust affordance, not summarised away at the group level. Takes `books` (plural) since S5, resolving each mention's citation off its own `book_id`. | S3, S5 |

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
  limit — citations are links and must survive a reload. First exercised at
  S3: the roster's `?q=&tier=&sort=` and the detail page's `?chapter=`
  (the timeline-to-mention-list sync).
- **`CharacterOut` (the roster list contract) has no per-chapter histogram** —
  only `CharacterDetailOut` (a single-character fetch) carries
  `mentions_per_chapter`. The roster row's sparkline can't show real data
  without either an SCR or an N+1 detail fetch per row; SCR-1
  (`plans/sprint-3/SCR.md`) asks for the former. Until it lands,
  `character-row.tsx` passes `<SparklineBars>` an empty histogram on purpose —
  it renders a labelled placeholder rather than fabricating a chapter shape.
- **`MentionOut` has a `page` but no `SpanBox`** — a mention's click-through is
  a plain `<PageRef>`, not a `?highlight=` deep link, because there is no
  span to highlight. SCR-2 (`plans/sprint-3/SCR.md`) asks for an optional
  `span` field, mirroring the citation highlighting `?highlight=` already
  supports (`plans/sprint-2/HANDOFF.md`).
- The chapter-detection carried gap (`plans/sprint-2/RETRO.md` §4 — zero
  chapters found on the real corpus until do1's Sprint 3 fix lands) means
  `mentions_per_chapter` and `chapterForPage`/`chapterKeyForPage`
  (`routes/book/chapter-lookup.ts`) may see one degenerate bucket or no
  chapters at all on real data. Both degrade correctly (a one-bar timeline,
  an unfiltered mention list) rather than crashing — this is expected
  Sprint 3 data, not a frontend bug.
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
  one). `axe` runs in CI from S9. **Wrap has to be set on every level that can
  overflow, not just the outermost `HStack`** — the page viewer's toolbar had
  an outer `wrap="wrap"` but its four-button zoom group didn't, and that group
  alone (`"Fit width" "Fit page" "100%" "200%"`) is wider than a 400px
  viewport's usable width.
- `openapi-fetch`'s configured `fetch` receives a `Request` instance, not a
  bare URL string — `String(request)` stringifies to `"[object Request]"`.
  Every test's `fetch` mock reads the real URL off `.url` instead
  (`input instanceof Request ? input.url : String(input)`), and route
  matching in a mock should check the URL shape (regex/pathname), not
  `.includes(path)` — a more specific path (`/pages/5`) is a substring away
  from colliding with a less specific one (`/books/{id}`).
- **Resetting state when a prop changes is not an effect** — see
  `chunk-inspector.tsx` and `page-viewer.tsx` (`if (prop !== tracked) { setTracked(prop); ...reset other state... }`
  during render, React's own documented pattern). `oxlint`'s
  `react/set-state-in-effect` flags the `useEffect([prop]) { setState(...) }`
  version as risking a cascading extra render.
- **The book filter and the series-position control are two different
  mechanisms, not one** (S5.11) — the book filter (`GraphFilters.bookFilter`)
  slices the already-fetched standing graph client-side and animates, same as
  family/tier/confidence; the series-position control
  (`limit_book_order`/`limit_chapter`) changes the server query and re-fetches
  a smaller graph outright, because spoiler correctness is a hard cut, not a
  visual filter a reader could toggle back on. Don't merge them into one
  `GraphFilters` field.
- **A citation now always carries its own book** — `MentionOut.book_id`,
  `AppearanceOut.book_id`, `PageRefOut.book_id`/`book_order`,
  `EvidenceOut.book_id`/`series_order` are all populated per item since the
  contract was designed multi-book-first. Never pass a single `bookId`/
  `bookTitle` prop down through a project-scoped component and apply it to
  every citation inside — resolve each citation's own book from a `books`
  map (`project-lookup.ts`'s `bookById`) instead. `mention-inspector-drawer.tsx`
  and `evidence-item.tsx` both had to be corrected for exactly this in S5.
- **`CharacterOut` (roster list) still can't do per-book intensity, only
  presence** (SCR-1, `plans/sprint-5/SCR.md`) — the same trade-off as Sprint
  3's sparkline gap, now on `<AppearanceStrip>`. **`mentions_per_chapter` is
  ambiguous across books** (SCR-2) — chapter numbers reset per volume, so it
  is never trusted directly for a multi-book character; the detail page
  derives its own histogram from mentions filtered to one selected book.

## Related

[web/AGENTS.md](../../../web/AGENTS.md) · [.agents/rules/web.md](../../rules/web.md) ·
[design/DESIGN.md](../../../design/DESIGN.md) · [query-path.md](query-path.md) ·
[plans/sprint-1/SCR.md](../../../plans/sprint-1/SCR.md) ·
[plans/sprint-1/HANDOFF.md](../../../plans/sprint-1/HANDOFF.md) ·
[plans/sprint-2/SCR.md](../../../plans/sprint-2/SCR.md) ·
[plans/sprint-2/HANDOFF.md](../../../plans/sprint-2/HANDOFF.md) ·
[plans/sprint-5/SCR.md](../../../plans/sprint-5/SCR.md) ·
[plans/sprint-5/HANDOFF.md](../../../plans/sprint-5/HANDOFF.md)

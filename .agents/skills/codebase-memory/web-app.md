# Web app

React 19 · TypeScript · Vite 8 · Chakra UI v3 · pnpm. Symbols over line numbers.

## Current state

**Built:** `web/src/app.tsx` (returns `<Box className="app">App</Box>`),
`web/src/main.tsx`, `web/src/design-system/theme.ts`,
`web/src/design-system/provider.tsx`, `.oxlintrc.json`, Vite config.

Everything else is S1+. `react-router` and `@tanstack/react-query` are **not yet
dependencies** — they land in S1.8/S1.9.

Note: `web/src/App.tsx` was renamed to `app.tsx`; both may appear in git status.
Lowercase is the convention.

## Planned structure (S1)

```
src/
  app.tsx                 router + providers
  routes/                 one folder per screen, lazy-loaded
  components/ui/          Chakra-composed primitives
  components/layout/      AppShell, TopBar, SideNav, PageHeader
  lib/api/                generated client + typed hooks
  lib/format/             page refs, chapter labels, durations
  design-system/          theme.ts (generated from tokens.ts), provider.tsx
```

## Routes

Declared in full at S1 with `<NotYetBuilt/>` placeholders — adding a route later
is a refactor, stubbing it now is a one-line swap.

Routes move to **project scope** in S5; `/books/:id/...` survives only for
book-local views (pages, chapters).

| Route | Screen | Sprint |
| --- | --- | --- |
| `/projects` | project list | S1 (as `/books`), S5 |
| `/projects/new` | create project (standalone \| series) | S5 |
| `/projects/:id` | books in series order, drag to reorder, add book | S5 |
| `/projects/:id/characters` | series roster + appearance strip | S3, S5 |
| `/projects/:id/graph` | series graph, book filter | S4, S5 |
| `/projects/:id/ask` | Q&A with citations | S6 |
| `/books/upload` | upload | S1 shell, S2 real |
| `/books/:id` | ingestion progress | S2 |
| `/books/:id/chapters` | chapters + chunk inspector | S2 |
| `/books/:id/pages/:n` | page viewer | S2 |
| `/books/:id/characters` | roster | S3 |
| `/books/:id/characters/:cid` | character detail | S3 |
| `/books/:id/graph` | graph explorer | S4 |
| `/books/:id/ask` | Q&A with citations | S6 |
| `/books/:id/review` | review queue | S7 |
| `/ops`, `/ops/evals` | dashboard, ablations | S8/S9 |

## Key components

| Component | Note | Sprint |
| --- | --- | --- |
| `<AsyncBoundary>`, `<EmptyState>`, `<ErrorState>`, `<LoadingSkeleton>` | Build once, properly — every later screen reuses them | S1 |
| `<PageRef page={n}>` | **The most-used component in the product.** A link, not a button. Accessible name includes book and page, never a bare number. | S1 |
| `<PageViewer>` | pdfjs-dist; `highlights` prop in the PDF coordinate space agreed with be1 in S2. Deep-linkable. | S2 |
| `<EvidenceItem>` | quote + page ref + assertion badge; `hearsay` must read differently at a glance | S4 |
| `<RelationArc>` | temporal sequence; a 1-state arc renders through the same path as a 3-state one, and a 3-book arc through the same path as a 1-book one | S4, S5 |
| `<AppearanceStrip>` | per-book presence band; needs a text equivalent — a coloured band alone is not an answer | S5 |
| Graph explorer | Cytoscape.js + `fcose`. Layout cached — recomputing on every filter makes it jump. **List view is an equal, not a stub.** | S4 |
| Review queue | `j/k/a/e/m/s/x/u`. Prefetch next 3; optimistic with undo. Target: 50 tasks in <8 min, no mouse. | S7 |

## Gotchas

- **Never hand-write API types.** `pnpm gen:api` regenerates
  `src/lib/api/schema.d.ts` from the live `/openapi.json`; it is committed and
  CI fails on drift.
- SSE event unions need **explicit discriminators** on the backend or
  `openapi-typescript` emits `unknown`.
- URL search params hold filters, selected entity, page, and the spoiler chapter
  limit — citations are links and must survive a reload.
- `localStorage` only for per-viewer conveniences (theme, reader's chapter
  position). Wrap in try/catch; it throws in private windows.
- Polling `refetchInterval` must return `false` on terminal states.
- **Design tokens are frozen** (`design-system/tokens.ts`, orchestrator-owned).
  A missing value is a DCR, not a local addition. See
  [design/DESIGN.md](../../../design/DESIGN.md).
- Colour is never the only channel — relation families carry a line style too.
- Every screen works at 400px; `axe` runs in CI from S9.

## Related

[web/AGENTS.md](../../../web/AGENTS.md) · [.agents/rules/web.md](../../rules/web.md) ·
[design/DESIGN.md](../../../design/DESIGN.md) · [query-path.md](query-path.md)

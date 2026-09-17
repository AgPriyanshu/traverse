# Sprint 1 · Frontend Engineer 1

**Branch:** `ai/fe1/sprint-1-foundations` · **Worktree:** `../traverse-wt/fe1`
**Read first:** [BRANCH.md](../../BRANCH.md), [sprint-1/README.md](README.md)

## Mission

The web app is currently one component returning `<Box>App</Box>`. Build the
shell the next seven sprints hang off: routing, theme, layout, a typed API
client generated from the real OpenAPI schema, data-fetching conventions, and
the loading/error/empty primitives every later screen reuses. No feature
screens beyond book list and upload — those arrive with their backends.

**Design constraint from the PRD:** this is a product about *fiction*, and the
UI should feel like a reading tool, not a compliance dashboard. Generous line
length, real typography, restraint with colour. The graph explorer in Sprint 4
is the only place that gets to be visually loud.

## Design input — read before writing any component

Open [design/DESIGN.md](../../design/DESIGN.md) and the Claude Design canvas URL
recorded there. Implement the artboards listed for **this sprint** in the
artboard map (§1). Use the frozen tokens from
`web/src/design-system/tokens.ts` — never a literal colour, spacing value, or
font size. Where the canvas and `DESIGN.md` disagree, DESIGN.md wins; where
something you need is missing from both, file a **DCR** (BRANCH.md §8) rather
than inventing a token in your worktree.

---

## Owned paths

```
web/src/**  web/index.html  web/package.json  web/vite.config.ts
web/tsconfig*.json  web/.oxlintrc.json  web/tests/**
```

Forbidden: everything under `api/`, `docker-compose.yml`, `web/Dockerfile`,
`web/nginx.conf` (DO1 owns the container story).

## Setup

```bash
cd ../traverse-wt/fe1/web && pnpm install
echo 'VITE_API_BASE_URL=http://localhost:8003' > .env.local
pnpm dev     # :5173
```

Port 8003 is your API slice. Until BE1/BE2 land, run the contract API from the
integration checkout — it returns correct empty shapes from the frozen route
stubs, which is exactly what you need.

---

## S1.8 — App shell

Add `react-router` v7, `@tanstack/react-query`, and keep Chakra v3 as-is.

```
src/
  app.tsx                 router + providers
  routes/                 one folder per screen, lazy-loaded
    books/                list, upload
    book/                 detail shell with tabs (Chapters · Characters · Graph · Ask)
  components/ui/          Chakra-composed primitives
  components/layout/      AppShell, TopBar, SideNav, PageHeader
  lib/api/                generated client + typed hooks
  lib/format/             page refs, chapter labels, durations
```

Route table — declare the whole Sprint 1–8 surface now, with `<NotYetBuilt/>`
placeholders for unbuilt screens. A route added later is a refactor; a route
stubbed now is a one-line swap.

```
/                         → redirect /books
/books                    library
/books/upload             upload
/books/:id                overview + ingestion progress
/books/:id/chapters
/books/:id/characters
/books/:id/characters/:characterId
/books/:id/graph
/books/:id/ask
/books/:id/review         (Sprint 7)
/ops                      (Sprint 9)
```

**Required primitives** (everything later reuses them, so build them once and
properly): `<AsyncBoundary>` (suspense + error boundary + retry),
`<EmptyState>`, `<LoadingSkeleton>`, `<ErrorState>` with the real error message
and a retry button, `<PageRef page={n}>` — the citation chip that appears on
every screen from Sprint 4 on.

Dark mode via `next-themes` (already a dependency), persisted, honouring
`prefers-color-scheme`. Contrast ≥ 4.5:1 in both themes (NFR-a11y) — verify
with a contrast checker, do not eyeball it.

*Acceptance:* Every route renders without console errors. Theme survives
reload. Keyboard tab order through the shell is correct and focus is visible.

## S1.9 — Typed API client

Generate from the live schema, do not hand-write types:

```json
"scripts": {
  "gen:api": "openapi-typescript http://localhost:8000/openapi.json -o src/lib/api/schema.d.ts"
}
```

Use `openapi-fetch` over the generated types. Wrap each endpoint in a TanStack
Query hook in `src/lib/api/hooks.ts`:

```ts
export const useBooks = () => useQuery({queryKey: ['books'], queryFn: ...})
export const useBookStatus = (id: string) =>
  useQuery({
    queryKey: ['books', id, 'status'],
    queryFn: ...,
    refetchInterval: (q) => isTerminal(q.state.data?.status) ? false : 2000,
  })
```

Commit the generated `schema.d.ts`. A CI check regenerates it and fails on
drift — that is how the frontend learns the backend changed a contract, and it
is worth the noise.

*Acceptance:* `pnpm gen:api && tsc --noEmit` clean. Deleting a field from a
backend response model produces a **compile error**, not a runtime `undefined`.

## S1.10 — Library and upload screens

**`/books`** — real data from `GET /api/books`. Card grid: title, author, page
count, chapter count, ingestion status pill, relative ingested-at. Genuine empty
state ("No books yet — upload a novel to begin") with a primary action, not a
blank page.

**`/books/upload`** — drag-and-drop with click fallback, PDF only, client-side
size cap of 200 MB with a clear message, filename and page-count preview where
cheap. Wire `POST /api/books`; it returns 501 this sprint, so render the error
path properly. **Rendering the 501 correctly is the acceptance criterion** — a
real error surface built now is a real success surface in Sprint 2.

**`/books/:id`** — the ingestion progress shell. Stage list from
`GET /books/{id}/status` rendered as a vertical stepper with per-stage state,
duration, and error text. PRD F1.1: "a 20-minute job with no visible progress
reads as broken." Build the component now; it gets real data in Sprint 2.

---

## Definition of Done

- [ ] All routes registered and reachable; unbuilt ones render a clear placeholder
- [ ] `tsc --noEmit` and `oxlint` clean
- [ ] Generated client committed; drift check wired for DO1's CI
- [ ] Dark and light both pass 4.5:1 on text and interactive elements
- [ ] Responsive at 400px — no horizontal scroll on any built screen
- [ ] `HANDOFF.md`: any API shape that was awkward to consume, as SCR candidates

## Escalate immediately if

- A frozen response model is unusable as-is (e.g. citations without page numbers,
  IDs missing from a nested object) → **SCR now.** Contract problems are ten
  times cheaper to fix in Sprint 1 than in Sprint 6.
- OpenAPI generation produces `unknown` for a union type → tell the orchestrator;
  SSE event models need explicit discriminators.

# Agent Instructions — frontend (`web/`)

React 19 · TypeScript · Vite · Chakra UI v3 · TanStack Query · React Router.

Read [../AGENTS.md](../AGENTS.md) first. Design direction and tokens live in
[../design/DESIGN.md](../design/DESIGN.md) — read it before writing any
component.

---

## Component layout

Structure complex function components with **section comments** so hooks, refs,
and effects stay easy to scan.

- Leading space after `//`, sentence case, trailing period: `// States.`
- Sections in **dependency order** — state and refs before the effects that use
  them; API hooks before the memos that consume their data.
- Repeat a section label when needed (`// Hooks.` before a hook, `// useMemos.`
  for values depending on it, `// Hooks.` again for another).

| Section | Purpose |
| --- | --- |
| `// States.` | `useState` declarations. |
| `// Refs.` | `useRef` declarations. |
| `// Context.` | `useContext` consumers. |
| `// Hooks.` | Router, form helpers, third-party hooks. |
| `// Apis.` | TanStack Query data hooks (`useBooks`, `useCharacter`, …). |
| `// useMemos.` | `useMemo` values. |
| `// Variables.` | Simple derived values (no hook). |
| `// Constants.` | Static config or literals. |
| `// useEffects.` | All `useEffect` calls, grouped. Prefer this over scattering them between handlers. |
| `// Handlers.` | Event handlers and callbacks (`const handleX = …`). |

Omit sections that are empty. Suggested order: States → Refs → Context → Hooks →
Apis → Variables → useMemos → useEffects → Handlers → early returns → JSX.

## `if` statements — always use braces

Never put the body of an `if` / `else if` on the same line as the condition. Even
a single `return`, `throw`, `break`, `continue`, or assignment uses a block.

```ts
if (!book) { return null; }        // good
if (!book) return null;            // bad
for (const c of chunks) { if (!c.page) { continue; } }
```

Same rule for `for` and `while`. Default for all new code in this repo.

## Data fetching

- **Never hand-write API types.** `pnpm gen:api` regenerates
  `src/lib/api/schema.d.ts` from the live `/openapi.json`; the generated file is
  committed and CI fails on drift. Deleting a backend field must produce a
  compile error, not a runtime `undefined`.
- Every endpoint is wrapped in a typed TanStack Query hook in
  `src/lib/api/hooks.ts`. Components call hooks, never `fetch` directly.
- Polling uses `refetchInterval` returning `false` on terminal states — an
  ingestion poll that never stops is a background CPU leak in an open tab.
- Streaming answers arrive over SSE with **discriminated** event types. Switch on
  `event.type`; never parse by shape.

## State

- Server state → TanStack Query. Do not mirror it into `useState`.
- URL state → search params. Filters, selected character, page number, and the
  spoiler chapter limit must all survive a reload and be shareable — citations
  are links.
- `localStorage` only for per-viewer conveniences (theme, the reader's chapter
  position). Wrap every read and write in try/catch; it throws in private
  windows.

## Styling

Chakra v3 with the generated theme. Use tokens, never literals — no hex colour,
raw `px`, or font size in a component. If you need a value that does not exist,
file a **DCR** (BRANCH.md §8); do not add it to `tokens.ts`, which is frozen.

When a feature grows its own stylesheet, **co-locate the partial with the
component that owns those class names** — `my-widget/_my-widget.scss` next to
`my-widget/my-widget.tsx`, with `index.ts` as the package export — rather than a
central `styles/` bucket. Shared `@keyframes` live in one partial at the feature
root so animation names are not duplicated in the bundle.

## Accessibility — not a polish task

These are acceptance criteria on specific stories, not a Sprint 9 sweep:

- Full keyboard navigation. The review queue's target is **50 tasks in under 8
  minutes without a mouse**; that is a design and implementation constraint from
  day one.
- Contrast ≥ 4.5:1 in **both** themes, verified with a tool, not eyeballed.
- **Colour is never the only channel.** Relation families are distinguished by
  colour *and* line style.
- The graph explorer needs a genuine non-visual equivalent — a structured
  per-character relationship list with the same click-through. It is also the
  better view on a phone.
- Every screen works at 400px with no horizontal scroll.
- `axe` runs in CI from Sprint 9; do not let findings accumulate until then.

## Citations are the product

Any component rendering a fact from the backend must render its page citation
with it. `<PageRef>` is a link, not a button; its accessible name includes the
book and page ("page 214 of Pride and Prejudice"), never a bare number. A fact
with no citation does not get rendered — that is the backend's contract and the
UI must not paper over a violation of it.

## Lint

`oxlint` with the react, typescript, and oxc plugins. `react/rules-of-hooks` is
an error. Run `pnpm lint` and `pnpm tsc --noEmit` before committing; a
type-clean app that fails `pnpm build` is still broken, so build before you call
it done.

---
description: Frontend architecture — routes, generated API client, citation rendering, design tokens
scope: paths
paths: web/src/**/*.ts, web/src/**/*.tsx, web/src/**/*.scss
---

# Web app

**See also:** [web/AGENTS.md](../../web/AGENTS.md) (style),
[design/DESIGN.md](../../design/DESIGN.md) (tokens and artboards),
[web-app.md](../skills/codebase-memory/web-app.md) (route and component map).

## Must

- Routes are declared for the whole product surface with placeholders for
  unbuilt screens. Adding a route later is a refactor; stubbing it now is a
  one-line swap.
- API types come from `pnpm gen:api`. The generated `schema.d.ts` is committed
  and CI fails on drift.
- Filters, selected entity, page number, and the spoiler chapter limit live in
  **URL search params** — citations are links and must survive a reload.
- Every rendered fact carries its `<PageRef>`.
- Use design tokens. A value that does not exist is a **DCR**, not a local
  addition — `tokens.ts` is frozen.
- Relation families are distinguished by colour **and** line style.

## Must not

- Hand-write a type that mirrors a backend response.
- Mirror server state into `useState`.
- Call `fetch` from a component. Wrap it in a typed query hook.
- Render a fact whose citation is missing. That is a backend contract violation
  and the UI must surface it, not hide it.
- Poll without a terminal condition.

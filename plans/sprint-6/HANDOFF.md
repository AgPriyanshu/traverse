# Sprint 6 — Handoff

## fe1 — S6.10 through S6.13

Picked up an interrupted session that had already built all four stories to
a high standard (192 Vitest tests, `pnpm lint`/`typecheck`/`build` clean,
the memory map already rewritten) but hadn't committed. Verified the
existing work rather than redoing it, found and closed one real gap, then
committed and pushed.

**What was already built, verified as correct against the frozen contracts:**

- **S6.10** — `/books/:id/ask` and `/projects/:id/ask` (`<AskScreen>`, shared).
  `use-conversation.ts` drives `POST /api/query`/`POST /api/query/{id}/respond`
  via a hand-rolled SSE reader (`lib/api/query-stream.ts` — no generated
  client covers a streaming body). Tokens and citations accumulate into an
  ordered `AnswerPart[]` so a citation splices in right where its claim ends,
  not appended as a footnote. Suggested questions rank the project's own
  roster by tier/mention count, falling back to three generic prompts for an
  empty roster. Route decision shown subtly ("answered from the character
  record"). Abstentions render as a considered answer (`<StatusDot
  tone="idle">`), not an error.
- **S6.11** — citations render as `<PageRef index>`, a superscript unicode
  figure, prefetched via `pageRenderQueryOptions` the instant the
  `CitationEvent` arrives (before the click). **Found incomplete: the
  citation click-through unmounted `<AskScreen>` and a plain `useState`
  conversation was lost on browser back** — the opposite of "get back to the
  answer without losing it." Fixed with `conversation-store.ts`, a
  scope-keyed cache outside React that `use-conversation.ts` reads on mount
  and writes on every update; its unmount cleanup also turns a still-
  streaming turn into a done one before the abort, so a paused stream reads
  as an answer, not a stuck spinner or an aborted-request error. New test:
  "preserves the conversation when a citation is followed to its page and
  back" (`web/tests/ask.test.tsx`), which drives a real `router.navigate(-1)`
  against the memory router (`web/tests/render.tsx` now returns the router
  instance for tests that need it).
- **S6.12** — `<InterruptCard>` (`components/ui/interrupt-card.tsx`): a
  clarifying question as option buttons plus a free-text fallback, posts to
  `/respond`, resumes the same stream in place. Built with no `QueryEvent`/
  `ReviewTask` import so Sprint 7's review queue can reuse it unchanged, per
  the brief.
- **S6.13** — `<ConversationThread>`/`<TurnView>`: scroll-anchored, a "Copy
  answer" button per done turn. `<ScopeBanner>` always shows the
  reading-position scope the frontend itself chose (`limit_book_order`/
  `limit_chapter`) with a link to clear it back to the whole series. It does
  *not* show a carried "about Elizabeth Bennet" character scope — the
  contract has nowhere to put one yet (see SCR note below).

**Filed:** `plans/sprint-6/SCR.md` SCR-1 — `CitationOut` has no `SpanBox`, so
every ask-screen citation degrades to a plain page link (correct page, no
highlighted quote); the third contract to hit the same gap Sprint 3/4 already
filed for `MentionOut`/`EvidenceOut`. Not blocking — flagged, not worked
around, since there's no client-side substitute for a real bounding box.
Also noted (not re-filed) that do1's own SCR-1 in this sprint —
`DoneEvent` missing `resolved_entities` — is the same underlying gap
`<ScopeBanner>` would need for the character-scope banner the S6.13 brief's
example implies; whichever lands covers both consumers.

**Verification (final pass, 2026-09-27):** `docker compose --profile test
run --rm test-web` — 193 Vitest tests passing across 15 files (was 192; +1
for the back-navigation regression test), lint and typecheck clean inside
that same containerized run. `pnpm build` clean on the host
(`tsc -b && vite build`, one pre-existing >500kB chunk warning on
`graph-explorer`, not from this sprint's files). Three commits on
`ai/fe1/sprint-6-ask`, pushed:

1. `feat(web): ask screen with streaming answers, inline citations, and a
   reusable interrupt [S6.10, S6.11, S6.12, S6.13]` — the inherited work,
   committed as-is.
2. `fix(web): preserve the conversation across a citation click-through
   [S6.11]` — the gap above.
3. `docs(sprint-6): memory map for the ask screen [S6.10-S6.13]`.

**Not verified against a live be2 backend** — S6.1-S6.9 (be2/be1's router,
retrieval, grounding, streaming, conversation memory) were not merged into
this worktree at time of writing; built and tested against the frozen
`api/contracts/api.py` `QueryEvent`/`QueryRequest`/`ClarifyResponse` with
realistic SSE mocks, same pattern as every prior sprint's frontend work here.
Re-run this sprint's demo script once be2's Sprint 6 lands on `ai-master`.

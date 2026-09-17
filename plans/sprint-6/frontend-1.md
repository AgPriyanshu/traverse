# Sprint 6 · Frontend Engineer 1

**Branch:** `ai/fe1/sprint-6-ask` · **Worktree:** `../traverse-wt/fe1`
**Owned:** `web/src/**`, `web/tests/**`

## Design input

Read [design/DESIGN.md](../../design/DESIGN.md) and the canvas; this sprint
implements the `ask` artboard. The `quote` type token and `<PageRef>` do the
heavy lifting — a cited answer should look like a reading note, not a chat
bubble.

---

**S6.10 Ask screen (F4.4).** `/books/:id/ask`. Consume be2's SSE stream and
render tokens as they arrive with **inline citation chips appearing in place**,
not collected in a footnote block at the end — the citation's value is that it
sits next to the claim it supports.

Landing state offers three suggested questions for the current book (PRD §9.1 —
a skimming visitor must get value in one click). Show the route decision subtly
("answered from the character graph") — it builds trust and it is free.

Abstentions must render as a *considered answer*, not an error. "Elizabeth has
no brother in this novel" is the system working correctly and should look like it.

**S6.11 Citation click-through.** Clicking a chip opens the page viewer at the
right page with the quote highlighted, via Sprint 2's highlight API. Deep-linkable
and back-navigable — a reader following four citations must be able to get back
to the answer without losing it.

*This single interaction is the product's promise.* It has to feel instant:
prefetch the page render as soon as a citation event arrives, before the click.

**S6.12 Clarification interrupt.** When the router is ambiguous it interrupts and
asks. Render the question with the candidate options (usually characters) as
selectable chips, post to `/query/{thread_id}/respond`, and resume the same
stream in place. This is the same interrupt mechanism Sprint 7's review queue
uses — build the component so Sprint 7 reuses it.

**S6.13 Conversation thread.** Turns with their citations, scroll-anchored,
copyable. Follow-ups carry scope, so show the active scope ("about Elizabeth
Bennet") with a way to clear it — invisible carried context is confusing when
it is wrong.

## DoD

- [ ] Streaming feels immediate; citations appear inline with their claims
- [ ] Citation → page → back preserves the answer
- [ ] Abstention reads as an answer, not a failure
- [ ] Interrupt component reusable by Sprint 7
- [ ] Keyboard-complete; 400px clean

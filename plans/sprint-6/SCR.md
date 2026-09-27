# Sprint 6 — Schema Change Requests

Checked `plans/sprint-6/SCR.md` in the sibling worktrees (be1, be2, do1)
before numbering: do1 has already filed SCR-1/SCR-2 there. fe1 starts at
SCR-1 in this file; the two will need reconciling (probably by renumbering
one set) at the merge train, same as any two branches touching the same new
path.

### SCR-1 · fe1 · 2026-09-27

**Need:** `CitationOut` (`api/contracts/api.py`) carries `book_id`,
`page_start`, `page_end`, `chapter_no`, `quote`, `chunk_id` — no `SpanBox`.

**Why:** S6.11's whole promise is "clicking a chip opens the page viewer at
the right page **with the quote highlighted**, via Sprint 2's highlight
API" — `<PageRef span>` already supports rendering a highlight
(`?highlight=x,y,w,h`, `routes/book/page.tsx`'s `parseHighlight`) because
`EvidenceOut` carries one. `CitationOut` doesn't, so every ask-screen
citation today degrades to a plain page link: correct page, no highlighted
span. This is the same shape of gap Sprint 3 (SCR-9) and Sprint 4 (SCR-10)
already filed for `MentionOut`/`EvidenceOut`'s own page-only citations —
`CitationOut` is now the third contract to hit it, and the query pipeline
(be2, S6.8's quote-span locator per `plans/sprint-6/backend-1.md`) is
specifically building the capability this would consume.

**Blocking:** no — the click-through still lands on the correct page
(`<PageRef>`'s `unavailable`/plain-link path), which is the acceptance
criterion for "get to the page that proves it"; only the highlighted span
inside that page is missing.

**Proposed:** add `span: SpanBox | None` to `CitationOut` at the next freeze,
populated from be1's S6.8 quote-span locator (`api/contracts/api.py`'s
`SpanBox` already exists — `EvidenceOut` is the precedent to copy). Once
present, `<CitationMark>` needs one line (`span={citation.span}`) to light up
end to end; no other frontend change required.

---

## Note on the ScopeBanner gap

`web-app.md`'s S6 gotcha ("no `QueryEvent` yet surfaces which characters a
follow-up resolved against") and do1's SCR-1 in this same sprint
(`resolved_entities` missing from `DoneEvent`) are the same underlying
contract gap seen from two different consumers — do1's eval harness and
fe1's `<ScopeBanner>` (S6.13's "about Elizabeth Bennet" carried-character
scope) both want the resolved entity set the router already has in hand.
Not re-filed here as a separate SCR; whichever of the two lands at the freeze
covers both.

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

### SCR-4 · be2 · 2026-09-27

**Need:** `LLMPurpose` (`api/contracts/enums.py`) has no entry for the S6.1
query router's classification call.

**Why:** the router makes one structured call per question to get the query
class and entity phrases (`api/query/router.py::classify_question`), same
shape as `structured_call`'s other callers, but every existing purpose is
wrong for it: `answer` is the narrative class's own free-text generation
call, and reusing it here would fold routing's latency and token cost into
the answer-generation numbers on the Sprint 9 cost dashboard. `adjudicate` is
the closest existing purpose in spirit — both are "pick one of a declared,
discrete set of outcomes" — so it is reused as an interim measure, documented
at the call site, rather than left blocking.

**Blocking:** no — routing works correctly today; this only affects how its
cost is attributed on the ops dashboard once that dashboard exists (Sprint
9). Every query's actual route/latency is still correctly recorded in
`QueryLog` regardless of which `LLMPurpose` tag the Langfuse trace carries.

**Proposed:** add `QUERY_ROUTE = "query_route"` to `LLMPurpose` at the next
freeze; `api/query/router.py` has one call site to update.

---

### SCR-5 · be2 · 2026-09-27

**Need:** confirming, not re-filing — do1's SCR-1 (`DoneEvent` needs
`resolved_entities`) and the `ScopeBanner` note above are the same gap S6.6's
own acceptance criterion runs into from a third angle: nothing in the SSE
contract lets a client see which characters a follow-up ("and her sister?")
actually resolved against, only that the answer changed.

**Why:** not blocking S6.6 itself — conversation memory is fully functional
server-side (`ConversationTurn.resolved_character_ids`, read back by
`api/query/conversation.py::carry_context` to resolve the next turn's "her
sister"), and the router's structured output already produces the entity
list `resolved_entities` would carry. It's a pure plumbing gap: whichever of
do1's or fe1's proposals lands, wiring it from `api/query/pipeline.py`'s
`_finish` is a one-line addition of already-computed data, not new logic.

**Blocking:** no.

**Proposed:** no separate change proposed — see do1's SCR-1 in their own
worktree's copy of this file, reconciled at the merge train same as fe1's
SCR-1 above.

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

---

### SCR-2 · do1 · 2026-09-27

**Need:** the frozen SSE contract (`api/contracts/api.py`'s `QueryEvent`
union — `TokenEvent | CitationEvent | RouteEvent | InterruptEvent | DoneEvent
| ErrorEvent`) carries citations (book/page/quote) but no resolved character
IDs or canonical names anywhere in the stream. `CitationOut` has no character
field, and neither `DoneEvent` nor `RouteEvent` carries one.

**Why:** S6.14's aggregation-completeness metric (`eval/answer_metrics.py`,
F4.1's "exactly five daughters, not a plausible four assembled from prose")
needs the *set of characters the system resolved the answer to*, compared
against `expected_entities` as an exact set. With no structured field to read,
`scripts/eval_answers.py` currently falls back to matching the gold roster's
canonical names and aliases against the answer's own text — a real answer to
"who are Mr Bennet's daughters" naming all five is scored correctly today, but
this proxy would silently under- or over-count if the prose phrases a name
differently than any labelled alias, or mentions a name in passing without
asserting membership. It measures the same thing the graph's aggregation
template is meant to guarantee, but through a strictly weaker channel than
reading the template's own result set would be.

**Blocking:** no — the harness is fully usable today: accuracy, citation
precision and abstention rate do not depend on this field, and aggregation
completeness against the text-matching proxy is still informative, just
noisier than reading resolved IDs would be.

**Proposed:** add `resolved_entities: list[str]` (canonical names or character
IDs) to `DoneEvent`, populated from whatever entity set retrieval already
resolved before generation (`query-path.md`'s "graph first" retrieval order
already has this list in hand at the point `DoneEvent` is emitted — this is
exposing it, not computing anything new). Batch into the Sprint 7 freeze
unless S6.1-S6.5's own implementation finds it cheaper to add now.

### SCR-3 · do1 · 2026-09-27

**Need:** `api/tests/pipeline/test_books_routes.py`'s frozen route-count
assertion (`assert len(response.json()["paths"]) == 40`) needs bumping to 43.

**Why:** S6.14/S6.15 added three do1-owned routes to `api/routes/ops.py`
(`GET /ops/answer-quality`, `POST /ops/judge-answer`, `GET /ops/query-latency`),
same class of change as SCR-3/SCR-16/SCR-4 in sprints 3/4/5. do1 does not own
`api/tests/pipeline/**` (be1) and cannot edit it directly. The final number may
need a further bump at the merge train if be2's S6.1-S6.5 query pipeline also
adds paths this sprint.

**Blocking:** no — same precedent as the prior three sprints' equivalent SCRs,
this is a known, understood test-count drift, not a real regression. Confirmed
locally: `pytest api/tests -q` is 460 passed / 1 skipped / this one known
failure with do1's Sprint 6 changes applied, nothing else red.

**Proposed:** bump the literal `40` to `43` (or higher, if be2 also added
routes) in that one assertion at the merge train, once the final count across
all four branches is known.

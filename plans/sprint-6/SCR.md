# Sprint 6 — Schema Change Requests

Checked `plans/sprint-6/SCR.md` in the sibling worktrees (be1, be2, fe1)
before numbering: none had filed one. do1 starts at SCR-1.

### SCR-1 · do1 · 2026-09-27

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

### SCR-2 · do1 · 2026-09-27

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

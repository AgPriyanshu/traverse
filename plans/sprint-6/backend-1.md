# Sprint 6 · Backend Engineer 1

**Branch:** `ai/be1/sprint-6-resolution` · **Worktree:** `../traverse-wt/be1`
**Owned:** `api/pipeline/**`, `api/extraction/**`, `api/routes/books.py`

## Mission

Two services on the query critical path, plus the instrumentation that proves
the latency targets. Both are be2's dependencies — ship by **Wednesday**.

---

**S6.7 Name resolution.** `resolve_names(book_id, text) -> list[CharacterRef]`.
Reuses the Sprint 3 alias index: exact → alias → nickname → fuzzy → embedding.
Must handle partial names ("Darcy" when both Mr Darcy and Georgiana Darcy
exist), returning **ranked candidates with scores rather than a guess** — be2's
router turns a genuine tie into a clarifying question, which it can only do if
you surface the ambiguity.

Target <50ms. This runs before every query; it cannot be an LLM call.

*Acceptance:* ≥95% top-1 on a labelled set of 100 references drawn from real
question phrasings. Ambiguous references return multiple candidates, never a
silent pick.

**S6.8 Quote-span locator.** `locate_quote(chunk_id, quote) -> PageSpan` →
page plus bounding boxes in the coordinate space agreed in Sprint 2.

Exact match first; fall back to normalised whitespace and fuzzy alignment, since
the model's quote will drift from the source by a character or two. A quote that
cannot be located returns `None` — **and be2 must then drop the citation rather
than cite a page it cannot point at.** A citation to the wrong span is worse
than no citation; it is the specific failure the PRD's 95% target guards.

*Acceptance:* ≥98% location rate for quotes that genuinely appear. Zero false
locations on a set of deliberately fabricated quotes.

**S6.9 Latency instrumentation.** Per-stage timing on every query — route,
resolve, graph, retrieve, rerank, generate, ground — into `query_log.latency_ms`
as a JSON object. TTFT measured at the first token leaving the API, not at
generation start; the gap between those two is usually where the budget goes.

*Acceptance:* Every query logs a complete stage breakdown. do1's dashboard reads
it with no further work.

## DoD

- [ ] Both services merged by Wednesday, signatures in `HANDOFF.md` on Day 2
- [ ] Name resolution <50ms p95, ambiguity surfaced not hidden
- [ ] Quote locator never returns a false position
- [ ] Stage timing complete enough to find a latency regression without a profiler

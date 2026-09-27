# Sprint 6 — Standup

## be1 — 2026-09-27

**Landed:** all three of be1's Sprint 6 stories — S6.7 name resolution
(`api/extraction/resolution.py::resolve_names`), S6.8 quote-span locator
(`api/pipeline/quotes.py::locate_quote`), S6.9 latency instrumentation
(`api/pipeline/timing.py::QueryTimer`). Picked this up from a prior session
that had already written all three modules, their tests, and the supporting
repository/render changes but left them uncommitted; verified the work
against the sprint spec and acceptance criteria (ambiguity surfaced not
guessed, `None` on an unlocated quote, TTFT measured at the API boundary),
fixed line-length lint (`ruff format`), committed in per-story chunks, and
ran verification. Signatures are in `HANDOFF.md`.

**Verification:** targeted run (resolution/quotes/timing/render/repository
tests, 48 cases) then the full suite — 489 passed, 1 pre-existing skip, no
regressions. `ruff check api` and `ruff format --check api` both clean.

**Next:** none — this was the full Sprint 6 scope for be1. Available for an
SCR if be2's S6.1-S6.6 integration surfaces a signature gap.

**Blocked:** not blocked.

## fe1 — 2026-09-27

**Landed:** all four stories (S6.10-S6.13) — the ask screen, streaming
answers with inline citations, citation click-through to the page viewer,
the clarifying-question interrupt (reusable for Sprint 7's review queue),
and the conversation thread with a clearable reading-position scope banner.
Picked this up mid-flight from an interrupted session that had already built
it well; verified rather than redid it, then found and fixed one real gap:
a citation click-through unmounted the ask screen and lost the whole
conversation on browser back, contradicting S6.11's own promise. Fixed with
a scope-keyed store outside React (`conversation-store.ts`).

**Next:** none — full sprint-6 scope for fe1. Would welcome SCR-1
(`CitationOut` needs a `span` field) landing so citations highlight the
exact quote rather than just opening the right page.

**Blocked:** not blocked. Built and tested against the frozen contracts with
realistic SSE mocks; not yet verified against a live be2 query pipeline,
since S6.1-S6.9 hadn't merged into this worktree at time of writing.

**Verification:** `docker compose --profile test run --rm test-web` — 193
Vitest tests, all passing; `pnpm lint`/`typecheck`/`build` all clean. Three
commits on `ai/fe1/sprint-6-ask`, pushed.

## be2 — 2026-09-27

**Landed:** all six of be2's Sprint 6 stories — S6.1 router, S6.2 templated
Cypher, S6.3 graph-constrained retrieval, S6.4 grounding/abstention, S6.5 SSE
streaming, S6.6 conversation memory, all in `api/query/**` plus the S6.3
filter wired into `api/retrieval/{repository,hybrid}.py` and `api/routes/
query.py`'s `/query` and `/query/{thread_id}/respond`. Picked this up from a
prior session, interrupted twice, that had already written all of it and its
tests but left the router's accuracy number as a literal placeholder never
actually measured; verified the implementation against the sprint spec
(read every module, cross-checked against `plans/sprint-6/backend-2.md`'s
DoD), found and fixed one drift bug (`router.py`'s docstring cited the wrong
SCR number for the missing `LLMPurpose` entry), then ran the router's own
`eval_router.py` against the live shared vLLM to get a real confusion matrix
rather than leave the placeholder in `HANDOFF.md`.

**Router accuracy (61 hand-labelled questions, live `Qwen/Qwen3-8B-AWQ`,
worktree run — directional per BRANCH.md §9, not an integration number):**
86.9% overall, **100% recall on `aggregation`** (this sprint's demo-critical
class — a misroute there is what turns into a hallucinated list). Real
weakness: `path` recall is only 66.7% (2 of 6 labelled `path` questions
misroute to `relationship_lookup` — `eval_router.py` only aggregates, so
which two is not something this run can name); 4/61 calls errored outright
before returning a classification, not merely misrouted. Full matrix and
per-class precision/recall in `HANDOFF.md` — reported as measured, not
rounded up.

**Abstention:** the demo's critical case holds under a real fixture —
`test_aggregation_abstains_for_a_gendered_hint_with_no_matching_gender`
pins that "What happens to Elizabeth's brother?" abstains rather than
handing back her sisters (the ontology has no gender attribute; `gender.py`
infers it from honorific aliases only and excludes unknowns rather than
including them). `test_aggregation_lists_every_daughter_exhaustively` pins
the complementary case — all five of Mr Bennet's daughters, not a plausible
subset.

**Also found in review, not fixed (documented in `HANDOFF.md`):**
`ConversationContext.summary` (S6.6's "beyond the cap" summarisation) is
computed and tested but nothing downstream actually reads it yet — a narrow
gap, only reachable in a conversation long enough to push a turn out of the
800-token budget.

**Verification:** full backend suite via `make test-api` (real Postgres +
real Neo4j) — 474 passed, 1 pre-existing skip, no regressions; `ruff check
api` and `ruff format --check api` both clean. Checked the shared
`traverse_int` Postgres for a running ingestion stage before starting
(`ingestionstage` — no such table in this environment, nothing running).
One commit (`66c2291`) plus this doc pass, pushed to
`ai/be2/sprint-6-query`.

**Next:** none — full Sprint 6 scope for be2. SCR-2 (`LLMPurpose.QUERY_ROUTE`)
and SCR-3 (`DoneEvent.resolved_entities`, confirming do1's/fe1's) filed,
both non-blocking.

**Blocked:** not blocked.

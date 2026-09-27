# Sprint 6 — Handoff

## be1 — S6.7 through S6.9

All three of be1's Sprint 6 stories are done, tested, and merged into this
branch (`ai/be1/sprint-6-resolution`). These are be2's dependencies for
S6.1-S6.6 — signatures below are stable and safe to import against.

**S6.7 — Name resolution (`api/extraction/resolution.py`).**

```python
async def resolve_names(
    session: SQLModelAsyncSession,
    project_id: UUID,
    text: str,
    *,
    conversation_characters: Sequence[UUID] | None = None,
) -> list[CharacterRef]
```

`CharacterRef` = `{character_id, canonical_name, score, method, importance_tier}`.
Project-scoped (a series project's roster spans every book in it), never an
LLM call. Cascade: exact/normalised -> honorific/name-order -> nickname ->
partial (bare surname/given name) -> fuzzy (typo tolerance) ->
conversation-anchored relative term ("her sister", needs
`conversation_characters` — that's the hook for be2's S6.6 conversation
memory to pass in). Returns candidates ranked by score, highest first;
**more than one entry at the top score is a genuine tie** — the router must
surface it as a clarifying question rather than picking the first one.
Reuses the Sprint 3 alias-cascade primitives in `api/extraction/normalization.py`.

New repository helpers it depends on, in `api/extraction/repository.py`:
`list_project_roster(session, project_id)` and
`kinship_candidates(session, *, project_id, referent_id, predicate)` (matches
either the stored direction of a `Relation` row or its ontology inverse via
`api/graph/ontology.py::inverse_of`).

**S6.8 — Quote-span locator (`api/pipeline/quotes.py`).**

```python
async def locate_quote(
    session: SQLModelAsyncSession, chunk_id: UUID, quote: str
) -> PageSpan | None
```

`PageSpan` = `{page: int, boxes: list[SpanBox]}` (`SpanBox` is the existing
S2.6 contract in `api/contracts/api.py`, same coordinate space as
`render_page`). Cascade: exact substring -> whitespace/curly-quote
normalised -> conservative fuzzy alignment (min 20 chars, 0.85 ratio) for a
one- or two-character drift. Search is scoped to the pages the chunk itself
claims (`DocumentChunk.pages`, falling back to `page_start..page_end`).
**Returns `None` when the quote cannot be located — treat that as "drop the
citation," never as "cite the chunk's first page anyway."** Zero false
positives on fabricated quotes was the acceptance bar and is what the test
suite (`api/tests/pipeline/test_quotes.py`) is built around.

Extracted `local_copy(storage_key)` (async context manager) out of
`render_page` in `api/pipeline/render.py` as a shared helper — both need a
real local file for `pypdfium2`. Added `repository.get_chunk_with_book` for
the joined chunk+book read (needs `Book.storage_key` and the chunk's page
range in one round trip on the query critical path).

**S6.9 — Latency instrumentation (`api/pipeline/timing.py`).**

```python
class QueryTimer:
    def stage(self, label: StageLabel) -> contextmanager  # accumulates, not overwrites
    def mark_ttft(self) -> None                            # idempotent, first call wins
    def as_dict(self) -> dict[str, int]                    # -> QueryLog.latency_ms
```

`StageLabel` is `Literal["route", "resolve", "graph", "retrieve", "rerank",
"generate", "ground"]`. `as_dict()` always includes `total_ms`; includes
`ttft_ms` only if `mark_ttft()` was called (a non-generating route, e.g.
aggregation, has no first token). **Call `mark_ttft()` at the point the
first token actually leaves the API, not when generation starts** — the gap
between those two is where the budget usually goes, and nesting TTFT inside
the `generate` stage's own duration would hide it.

This module only measures; be2 owns instantiating one `QueryTimer` per
query, wrapping each pipeline stage in `.stage(...)`, and persisting
`.as_dict()` into `QueryLog.latency_ms` (`api/db/models/ops_model.py`,
migration 0011).

**Not done, and not blocking:** no route in `api/routes/books.py` calls
these directly — none of S6.7-S6.9 required a route change per the sprint
plan; they're internal services for be2's query pipeline to import. If S6.1
turns out to need a thin wrapper route (e.g. for the frontend's own
debugging), that's an SCR against `api/routes/books.py`, not a scope change
here.

**Verification:** targeted tests (48) plus the full suite (489 passed, 1
pre-existing skip) both green in the `test` container; `ruff check`/`ruff
format --check` clean across `api/`. See STANDUP.md for the run details.

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

## be2 — S6.1 through S6.6

All six stories landed. Router → resolve → graph-or-retrieve → grounding →
SSE → conversation memory, end to end in `api/query/`. Built against be1's
S6.7-S6.9 exactly as documented above.

**S6.1 Router (`api/query/router.py::classify_question`).** One structured
call, `RouterOutput = {route, subject_phrase, object_phrase, predicate_hint}`.
Targets the frozen 7-value `QueryRoute` enum (PRD F4.1 names 6;
`series_arc` was added on top when Sprint 5 built series-arc support). Uses
`LLMPurpose.ADJUDICATE` as an interim stand-in for a call purpose that
doesn't exist yet — **SCR-2** filed, non-blocking.

Router confusion matrix, 61 hand-labelled questions
(`api/tests/fixtures/query/routing_questions.jsonl`), measured against the
live shared vLLM (`Qwen/Qwen3-8B-AWQ`), not a stub — per BRANCH.md §9 this
is a worktree run, not an integration one, so treat it as directional:

```
accuracy: 86.9% (61 questions)
errors (call failed, not merely misrouted): 4

class                  precision    recall  support
aggregation               100.0%    100.0%        8
ambiguous                 100.0%     87.5%        8
character_lookup          100.0%    100.0%       10
narrative                  81.8%    100.0%        9
path                      100.0%     66.7%        6
relationship_lookup        81.8%    100.0%        9
series_arc                100.0%     85.7%        7

confusion (expected -> predicted): count
  aggregation -> aggregation: 8
  ambiguous -> ambiguous: 7
  ambiguous -> narrative: 1  <-- MISROUTE
  character_lookup -> character_lookup: 10
  narrative -> narrative: 9
  path -> path: 4
  path -> relationship_lookup: 2  <-- MISROUTE
  relationship_lookup -> relationship_lookup: 9
  series_arc -> narrative: 1  <-- MISROUTE
  series_arc -> series_arc: 6
```

The headline number for this sprint's demo — **`aggregation` recall is
100%** (8/8) — holds: a misrouted aggregation question is the failure mode
that turns into a hallucinated list, and it did not happen once in this run.
Two real weaknesses, reported as measured, not rounded up:

- **`path` recall is 66.7%** (4/6) — two of the seven labelled `path`
  questions were classified as `relationship_lookup` instead.
  `eval_router.py` only aggregates the confusion matrix, not a per-question
  log, so which two is not something this run can name — worth adding
  before the next labelling round, rather than guessing at a pattern from
  the fixture text alone. Consequence in the pipeline either way:
  `relationship_lookup`'s template only matches a direct edge, so a
  misroute here doesn't hallucinate — it abstains or returns nothing where
  a real multi-hop path exists, rather than fabricating a wrong answer — but
  it does under-serve the question.
- **4 outright call errors** (schema/JSON failures, not misroutes) out of 61 —
  suspected to be the same runaway-generation failure mode `api/llm/client.py`
  documents (`max_tokens` cuts off a reasoning-shaped completion before valid
  JSON closes it), not something specific to routing. Worth a retry-with-
  shorter-budget policy at the next hardening pass, not filed as a blocking
  SCR since `classify_question`'s caller (`pipeline.answer_question`) already
  treats a router exception as a recoverable `ErrorEvent`, never a crash.
- `narrative` and `relationship_lookup` precision (81.8% each) is arithmetic
  fallout from the two `path` misses and one `series_arc` miss landing there,
  not an independent failure mode.

**S6.2 Templated Cypher (`api/query/templates.py`).** One declared,
parameterised statement for `relationship_lookup` and `aggregation` (the two
classes that need a real Neo4j traversal beyond what an existing repository
read covers); `character_lookup`/`series_arc` reuse existing Postgres reads,
`path` reuses `graph.queries.shortest_path`. `run_template` rejects any slot
set not matching the template's declared params exactly. No `inverse: false`
filtering in these templates — unlike `graph/queries.py`'s whole-graph
render, a directional aggregation needs *both* materialised copies of a fact
to be direction-agnostic (see the module docstring). Structural proof (AST
scan of every `.run()`/`.execute_query()` call in `api/query/**` and
`api/routes/query.py`, failing on anything but a bare name/attribute/literal
argument): `api/tests/query/test_no_freeform_cypher.py`.

**S6.3 Graph-constrained retrieval (`api/query/retrieval.py`).** Constrained
hybrid search first (chunks mentioning a resolved character, via a new
`CharacterMention` `EXISTS` filter actually wired into
`api/retrieval/repository.py::dense_search`/`lexical_search` — previously
accepted-and-ignored), whole-project fallback only when that's empty.
`SearchResultOut.tier` now reports `"graph_constrained"` or `"unconstrained"`
on every `hybrid_search` call (previously `None` always) —
**`api/tests/query/test_search.py` updated** for the new contract.

**S6.4 Grounding + abstention (`api/query/grounding.py`,
`api/query/generation.py`).** The five graph-derived classes are grounded by
construction — they render straight from a retrieved `CharacterDetailOut`/
`RelationOut`, never free text, so there is nothing for a grounding check to
catch. `narrative` alone free-generates and is checked by a deterministic
content-word-overlap threshold (0.6) against its own retrieved chunks — a
documented simplification, not semantic entailment; a paraphrase that flips
a negation would still pass. Abstention: `grounding.abstain()`, used whenever
resolution finds nobody, a template finds no edge, or nothing clears the
overlap threshold.

**Gendered aggregation (`api/query/gender.py`) — the demo's critical case.**
The ontology has no gender attribute, so a naive `child_of`/`sibling_of`
aggregation for "daughters" or "brother" returns every child/sibling
regardless of gender. "What happens to Elizabeth's brother?" would otherwise
come back with her sisters instead of abstaining — exactly the wrong kind of
answer F4.4 forbids. Fixed by inferring gender from honorific-titled aliases
only (`Mr`/`Miss`/etc., reusing `api.extraction.normalization.gendered_title`)
and excluding — not defaulting to include — any candidate with no such
signal. Pinned by
`api/tests/query/test_pipeline.py::test_aggregation_abstains_for_a_gendered_hint_with_no_matching_gender`.
**Known limitation:** a real character with no honorific alias on record is
invisible to a gendered aggregation query — under-inclusive by design (see
the module docstring), but worth knowing before trusting a "sons" or
"daughters" count against a real corpus.

**S6.5 Streaming (`api/routes/query.py`).** `POST /query` and
`POST /query/{thread_id}/respond` both wrap
`api/query/pipeline.py::answer_question` in an SSE `StreamingResponse`
(`media_type="text/event-stream"`, one JSON-serialised `QueryEvent` per
`data:` frame). Narrative tokens are **buffered until grounding completes**,
not streamed live — TTFT is still measured against the raw model stream
(`QueryTimer.mark_ttft()`), but nothing reaches the wire until it has passed
the grounding check, because a sentence shown and then silently dropped is
the "hedge instead of remove" failure F4.4 forbids, just staged over SSE
instead of in the text. Every terminal branch (abstention, a graph-derived
answer, a grounded narrative one) funnels through one function
(`pipeline._finish`) that emits the `token`/`citation` events and then
`done` — this replaced a real bug caught by
`test_character_lookup_abstains_for_an_unknown_character` where an early
abstention produced a `done` event with no visible answer text at all.

**S6.6 Conversation memory (`api/query/conversation.py`).** `Conversation`/
`ConversationTurn` persisted every turn. Context is **token-budgeted, not
turn-count-capped** (`_CONTEXT_TOKEN_BUDGET`, chars/4 estimate): the most
recent turns' `resolved_character_ids` feed straight into
`resolve_names(..., conversation_characters=...)` for the next question, so
"and her sister?" resolves against whoever the previous turn was about. A
turn pushed out of the budget is summarised in one line built from its own
`resolved_names` — no second LLM call. `set_scope` records the reading
position each turn was answered at onto the `Conversation` row, but nothing
in the SSE contract yet lets a client *see* which characters a turn
resolved against (see the SCR-3 note below).

**Known gap, found in review, not fixed here:** `ConversationContext.summary`
(the one-line "Earlier in this conversation, also discussed: ..." built for
turns the token budget pushed out) is computed and pinned by
`test_carry_context_drops_turns_beyond_the_token_budget_and_summarises`, but
nothing downstream reads it — `_resolve_phrase` only consumes
`context.character_ids`, and neither `router.classify_question` nor
`generation.stream_narrative_draft` takes a context-text parameter. In
practice this only bites a conversation long enough to push a turn out of
an 800-token budget (~4-8 turns discussing the same characters), at which
point that turn's characters stop feeding name resolution and the summary
that was supposed to compensate is inert. Not a DoD blocker (none of the
five DoD lines depend on it) and not fixed here rather than widen this
session's scope into prompt changes on an already-tuned grounding/generation
path with no dedicated test for the wiring; flagging it plainly instead of
leaving it silently unused.

**Filed:** SCR-2 (`LLMPurpose.QUERY_ROUTE` doesn't exist yet — `ADJUDICATE`
reused as an interim stand-in, non-blocking) and SCR-3 (confirming, not
duplicating, do1's SCR-1 / fe1's `ScopeBanner` note — `DoneEvent` needs a
`resolved_entities` field; the data is already computed, this is pure
plumbing whenever one of those lands).

**Not measured here, by design (BRANCH.md §9 — no worktree timing claims are
valid):** p95/TTFT against a real book. Real citation precision, answer
accuracy, and abstention rate against a gold question set are do1's S6.14
harness to run against my pipeline once merged — everything above was
verified with real Postgres + real Neo4j but synthetic, hand-built fixture
data, not the shared corpus.

**Verification:** targeted suite (`api/tests/query`, `api/tests/graph`,
`api/tests/relations`, `api/tests/retrieval`) — 145 passed, 1 pre-existing
skip; `ruff check`/`ruff format --check` clean across the touched paths.
Re-verified against the full backend suite in a fresh session
(`make test-api`, real Postgres + real Neo4j) — 474 passed, 1 pre-existing
skip, no regressions; `ruff check api`/`ruff format --check api` both clean.
The router accuracy numbers above are from that same session's live run
against the shared vLLM. Final numbers also in `STANDUP.md`.

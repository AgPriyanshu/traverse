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

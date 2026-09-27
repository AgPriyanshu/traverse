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

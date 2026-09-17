# Agent Instructions — backend (`api/`)

Python 3.11+ · FastAPI · Celery · SQLModel/SQLAlchemy async · LangGraph · Neo4j ·
Docling · vLLM.

Read [../AGENTS.md](../AGENTS.md) first — it covers comments, secrets, testing,
commits, and the memory-before-exploration rule that applies here too.

---

## Docstrings

Use **Google style** for **functions and methods only**. Do **not** add
class-level docstrings.

- Keep class names self-explanatory (`DocumentChunker`, `RelationAggregator`,
  `AliasResolver`) instead of describing the class in a docstring.
- Docstring every **public** function and method; skip private helpers when
  behaviour is obvious from the name.
- Summary: imperative one-liner; optional extended description after a blank line.
- Sections, only when relevant: `Args:`, `Returns:`, `Raises:`, `Yields:`,
  `Note:`, `Example:`.
- Reference code with ``double backticks``.
- Skip `Args:` when there are no parameters; skip `Returns:` when the return is
  `None` and obvious.

```python
"""Assemble chunks into batches that fit the model's context window.

Counts with the model's own tokenizer rather than a characters/4 estimate;
prose with dialogue tokenizes differently and the error compounds across a
batch into a context overflow.

Args:
    items: Chunks to batch, in document order.
    max_context: Model context window in tokens.
    output_reserve: Tokens held back for the structured response.

Returns:
    Batch plans covering every item exactly once.

Raises:
    ValueError: If ``output_reserve`` exceeds ``max_context``.
"""
```

## Formatting

- Always put a blank line before a `return`, unless the `return` is the first
  line of the function body.
- Store a return value in a meaningfully-named variable, then return that
  variable — do not `return` a computed expression directly. Exception: a
  trivial pass-through (`return self._driver`, `return name`) needs no extra
  assignment.
- `ruff` enforces the rest: line length 88, `E`, `F`, `I`, `UP`, `B`, `SIM`.
  Run `ruff check --fix` and `ruff format` before committing.

> **Known config bug:** `pyproject.toml` has
> `[tool.ruff.lint.isort] known-first-party = ["app"]`, but this package is
> `api`. Import sorting is therefore wrong. Fix it to `["api"]` — orchestrator
> lands it at the next contract freeze; do not fix it in a worktree, it touches
> a shared file.

## Imports

Choose **relative** or **absolute** by whichever path is **shorter**. When equal,
prefer relative.

- **Same package** (siblings within one module tree, e.g. anything under
  `api.pipeline`): **relative** — `from .chunking import DocumentChunker`.
- **Cross-package** (different top-level areas under `api/`, e.g.
  `api.pipeline` → `api.llm`): **absolute** — `from api.llm import structured_call`.

Keep stdlib / third-party / local groups per existing file conventions.

## Async

Everything that touches I/O is async. Specifically:

- **Database:** `SQLModelAsyncSession` via `db_session()` / `get_session()`.
  Never open a sync session.
- **Neo4j:** the long-lived `AsyncDriver` singleton from `api/graph/client.py`.
  **Never construct a driver per call** — it opens a fresh connection pool each
  time and collapses under upsert load.
- **LLM:** `api/llm` is async throughout and bounded by a shared semaphore. Do
  not fan out unbounded concurrency from a Celery worker; vLLM runs
  `--max-num-seqs 16` and an unbounded fan-out just queues and times out.
- **Celery tasks** are sync entry points that wrap an async body:
  `return asyncio.run(_async_impl(...))`.

## Database access

- All DB access goes through a **repository module** in the owning package
  (`api/pipeline/repository.py`, `api/graph/repository.py`). Views, tasks, and
  nodes call repositories; they do not build queries inline.
- **Bulk insert in one statement.** Inserting 1,100 chunks row-by-row is a
  30-second stall — use a single `insert().values([...])`.
- **Respect `human_verified`.** Every write path that touches `character`,
  `relation`, `chapter`, or their evidence must skip or diff against verified
  records, enforced at the repository layer rather than per call site. A human
  correction that gets overwritten kills the review feature.
- Postgres is the source of truth; Neo4j is a rebuildable projection. Never
  write a fact to Neo4j that does not exist in Postgres.

## Structured LLM output

All model calls go through `api/llm` — never instantiate `ChatOpenAI` elsewhere.

- Call with a `purpose` (`chapter_classify`, `character_extract`,
  `relation_extract`, `adjudicate`, `answer`, `judge`). Routing policy maps
  purpose → model; call sites never pick a model.
- Use `structured_call(...)` with a Pydantic schema. It retries once on
  `ValidationError` with the error appended, then raises.
- Classify failures correctly: `TransientLLMError` is retried by Celery,
  `PermanentLLMError` is not. Retrying a malformed prompt four times wastes
  twenty minutes.
- Every call is traced in Langfuse with `purpose` and `book_id`. Do not add a
  call path that bypasses this — the cost dashboard reads those tags.

## Domain invariants

These are enforced in code and must not be relaxed to make a test pass:

| Invariant | Where | Why |
| --- | --- | --- |
| Every chunk has a non-null page range | ingestion, DB constraint | Page-exact citation is the product |
| No relation edge without ≥1 evidence item | `graph.upsert` guard | PRD F3.2 — an unevidenced edge is a hallucination with a UI |
| A quote must appear in its cited chunk | relation validator | Catches fabricated evidence outright |
| Subject and object must match a known character | relation validator | Off-roster names are invention |
| Human-verified values are never overwritten | repository layer | PRD F5.4 |
| Temporal changes close the old edge, never overwrite it | `relations.aggregate` | The history is the interesting part |

## Testing

Per [../AGENTS.md](../AGENTS.md): through the compose `test` service, targeted
runs by default, ask before a full suite.

- Repository and pipeline tests run against a **real Postgres**, not mocks. The
  interesting failures are constraint and transaction failures.
- LLM calls are stubbed at the `api/llm` boundary, not at the HTTP layer.
- Fixtures live in `api/tests/fixtures/`; use the 20-page fixture novel, not a
  real one — CI must not take 25 minutes.

# Sprint 2 — HANDOFF

Contracts other agents consume. Owner in brackets. Append, do not rewrite.

---

## do1 → be1 · `api/ops/storage.py` (S2.15)

```python
async def put_stream(key: str, fileobj: IO[bytes], *, content_type: str | None = None) -> None
async def exists(key: str) -> bool
async def presigned_get(key: str, *, expires_in: int = DEFAULT_PRESIGN_TTL_S) -> str
async def delete_prefix(prefix: str) -> int   # returns the count removed — ETH-2's deletion primitive
```

All four run their boto3 call in a thread (`asyncio.to_thread`) — none of them
block the event loop. `put_stream` streams via `upload_fileobj` with a fixed
multipart chunk size, so a 200MB `UploadFile.file` holds flat memory; do not
`.read()` it whole before calling this.

`presigned_get` signs against the **public** endpoint (`MINIO_ENDPOINT`, e.g.
`localhost:9002`), not the in-network one (`minio:9000`) — the URL leaves the
container and reaches a browser, so it must resolve from there. Default TTL
15 minutes (page renders regenerate on demand; a cache is not a database).

Bucket is `settings.minio_bucket` (`traverse-be1`/`traverse-be2`/`traverse-int`
per BRANCH.md §4 — already the value your worktree `.env` sets). Object keys
are yours to choose; suggested shape for page renders is
`books/{book_id}/pages/{page}.png` — the MinIO lifecycle rule already
installed (`docker/minio/init-buckets.sh`) expires exactly `books/*/pages/*`
after 30 days, so a different prefix silently opts out of that cleanup.

**Retroactive SCR-2** (`plans/sprint-2/SCR.md`): `boto3` is a Dockerfile-layer
stopgap, not yet in `api/pyproject.toml` — it'll be a plain import once the
Sprint 3 freeze lands it properly. Nothing to do on your side; noted so the
stopgap doesn't look like an accident if you go looking for it in `uv.lock`.

## do1 → be1 · `api/ops/metrics.py` + `api/ops/tracing.py` (S2.17)

```python
def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None
```

Call after every LLM call with the exact model id the call resolved to
(`settings.llm_model`, not `"local"`/`"api"`) and set the result on
`StageRecord.cost_usd` / `QueryLog.cost_usd`. Returns `None` — not `0.0` — for
a model with no `COST_TABLE` entry, so a genuinely uncosted call is
distinguishable from a free one; `GET /api/ops/metrics` (below) sums whatever
is there and a `None` never silently becomes zero upstream of it.

```python
def run_trace_url(run_id: UUID) -> str | None
def stage_span(run_id: UUID, book_id: UUID, stage: StageName) -> AbstractContextManager[None]
```

Two call sites, both in `api/workers/stages.py` (forbidden to do1 — this is
the whole reason it's a handoff and not a same-commit change):

1. **`open_run()`**, in the branch that creates a new run (not the "return
   existing" branch — a resumed run keeps its trace, it doesn't get a new
   one):

   ```python
   run = IngestionRun(book_id=book_id, started_at=utcnow())
   run.trace_url = tracing.run_trace_url(run.id)   # <-- add this line
   session.add(run)
   await session.flush()
   ```

   `run.id` is already populated at construction (`default_factory=uuid.uuid4`
   on the model) so this needs no flush first. `run_trace_url` degrades to
   `None` on any Langfuse failure — never raises, safe unconditionally.

2. **`stage()`**, wrapping the body:

   ```python
   record = await _begin(book_id, stage_name)
   started = time.monotonic()

   try:
       with tracing.stage_span(record.run_id, book_id, stage_name):  # <-- add this line
           yield record
   except BaseException as exc:
       await _settle(record, StageState.FAILED, started, exc)
       raise

   await _settle(record, StageState.SUCCEEDED, started, None)
   ```

   `stage_span` is a no-op context manager when Langfuse has no keys (default
   compose profile), so this is safe to add unconditionally — no env check
   needed at the call site.

Both are two-line changes, both degrade to no-ops with tracing disabled, and
both are covered by `api/tests/ops/test_tracing.py` on do1's side already —
nothing further to test on yours beyond confirming ingestion still runs.

## do1 → everyone · `/api/ops/*` now real, not stubs (S2.17 / S2.18)

`GET /api/ops/metrics`, `GET /api/ops/pipeline/runs`, and
`GET /api/ops/pipeline/dead-letter` are wired to real handlers
(`api/ops/pipeline_status.py`) as of this commit — no more 501. All three are
read-only over `ingestion_run`/`ingestion_stage`, so they light up with real
data the moment `open_run`/`stage()` are writing rows (already true since
Sprint 1) and with a real `trace_url` once the two-line change above lands.

`fe1`: the F7.1-shaped dashboard data source is live now, ahead of Sprint 9 —
`GET /api/ops/pipeline/dead-letter` is exactly the feed S2.12's retry-button
UI wants for "book landed in dead-letter with the failing stage and error
text" (Sprint 2 demo script, step 7).

## do1 → be1 · the S2.16 corpus is real (`corpus/manifest.json`)

`make seed` now fetches, licenses and paginates the real five-novel PRD §7
corpus (`scripts/seed_corpus.py`) instead of Sprint 1's EPUB-only stub.
Output lands in `corpus/downloads/*.pdf` (gitignored, rebuild with `make
seed`); `corpus/manifest.json` (committed) pins page count and both SHA-256s
per book:

| key | title | pages (our pagination) |
|---|---|---|
| `pride-and-prejudice` | Pride and Prejudice | 245 |
| `wuthering-heights` | Wuthering Heights | 211 |
| `frankenstein` | Frankenstein; or, the Modern Prometheus | 124 |
| `the-great-gatsby` | The Great Gatsby | 111 |
| `anna-karenina` | Anna Karenina | 685 |

**This is the corpus `api/tests/fixtures/chapter_truth/*.json` must hand-label
against** (backend-1.md). Pagination is a pure function of the stripped
Gutenberg text and the layout constants at the top of `seed_corpus.py` (Letter
page, 72pt margin, 10pt Courier, 78 cols × 54 lines) — deterministic and
already re-run once to confirm byte-identical PDFs, but if you ever see a
labelled page number stop matching the corpus, check whether those constants
moved before assuming your extraction regressed. `corpus/LICENSES.md` has the
per-book source URL and Gutenberg ebook id if you need to cross-check a page
against the original.

Note the `pride-and-prejudice` source (Gutenberg id 1342) is the 1894
Saintsbury/Thomson illustrated edition, not a bare-text edition — it carries a
preface and a "List of Illustrations" front section before Chapter I, and at
least one chapter heading is transcribed as `Chapter I.]` (trailing bracket,
title case, embedded in an `[Illustration: ...]` block) rather than the
`CHAPTER I.` most other chapters use. Real messiness from a real public-domain
scan, left as-is rather than cleaned up — probably useful noise for the
regex+LLM-fallback chapter segmenter (S2.3) to prove itself against.

## do1 → be1 / be2 · `make test-integration` activates itself on your merge

`scripts/test_integration_ingestion.py` uploads a synthetic ~20-page fixture
novel through the real API (`POST /api/projects/{id}/books`), polls
`/status`, then asserts `pipeline.embed_chunks` succeeded and every chunk/
chapter carries page provenance. Right now it gets a 501 from the upload
endpoint (S2.1 not merged into this checkout) and exits 0 with a clear "not
merged yet" message — **this is expected and not a bug to fix**. The moment
your S2.1 branch merges into `ai-master`, this script starts asserting for
real with no change on either side. Same pattern in
`scripts/nightly_corpus_ingestion.py` (the real five-book corpus, wall clock +
cost posted to `$GITHUB_STEP_SUMMARY`, S2.18's NFR-perf trend line) — also
currently skip-everything-and-exit-0 for the same reason.

Both scripts create their fixture project by raw SQL
(`docker compose exec db psql`) rather than via `POST /projects`, because
that route is S5.9 (Sprint 5) and doesn't exist yet. **Gotcha worth knowing if
you ever seed a row into `project`/`book`/anything with a native enum column
by hand:** SQLAlchemy's `Enum` type stores the Python member's *name*, not its
`.value` — `project.kind` is the literal string `'STANDALONE'`, not
`'standalone'` (`ProjectKind.STANDALONE.value`). Cost me one failed insert
finding this; saving you the same.

## do1 → orchestrator · known gaps, flagged rather than silently skipped

- **`make test-integration`'s wall-clock budget (<8 min) is unverified.** The
  Makefile target now does cold-boot + health + unit tests + the fixture
  ingestion script in sequence; I did not run it end to end because doing so
  tears down (`make down`) the shared singleton `traverse` stack every other
  agent's worktree points at (BRANCH.md §4), and it was up and healthy for
  everyone when I started. Each piece is verified individually (cold-boot
  pattern already proven by `compose-smoke` in CI; the ingestion script
  verified live against the running stack). Whoever runs the actual merge
  train should time it once for real and adjust if it's over budget.
- **The nightly job's wall clock is not the number NFR-perf is judged on.**
  `runs-on: ubuntu-latest` has no GPU, so it runs `INFERENCE_MODE=api`. Fine
  for a cost/trend line starting now; swap to a GPU-labelled self-hosted
  runner in Sprint 9 for the number that actually gates ship.
- **SCR-2 (boto3) should have been filed at S2.15, not now.** Filed
  retroactively in `plans/sprint-2/SCR.md` — flagging for the retro per
  BRANCH.md's own "two blocking SCRs... is a retro action item" spirit, even
  though this one wasn't blocking; the process gap (claiming "SCR filed" in a
  commit message without actually filing it) is the thing worth a retro line.

---

## be2 → be1 : `api/llm/` substrate (S2.7 / S2.8) — landed on `ai/be2/sprint-2-ingestion`

Commit `4f34680` on my branch (not yet on `ai-master` — merge train order is
do1 → be1 → be2 → fe1, so be1 will not literally `import api.llm` until after
their own merge, but the branch is ready to rebase onto today). Importing
`api.llm` opens no connection and builds no client — safe to import at module
scope.

### `structured_call` — the call be1 uses for every model call

```python
async def structured_call(
    prompt: str,
    schema: type[T],          # T bound to pydantic.BaseModel
    *,
    purpose: LLMPurpose,
    book_id: str | None = None,
    stage: str | None = None,
) -> T
```

- Routes to a model by `purpose` alone — call sites never name a model.
- Retries once on schema-validation failure, appending the validation error
  to the prompt; raises `PermanentLLMError` if the second attempt also fails.
  Both attempts are recorded on one Langfuse generation (`attempt` in
  metadata) — a silent retry would corrupt the Sprint 9 cost breakdown.
- Bounded by a shared `asyncio.Semaphore` (`settings.llm_max_concurrency`,
  default 8) held for the full call including the retry — do not add your
  own concurrency limiting around this, it will compound.
- Raises `TransientLLMError` for anything Celery should retry (dropped
  connection, timeout, 429, 5xx) and `PermanentLLMError` for everything else
  (400, malformed input, schema still invalid after the retry). Both are
  `api.workers.errors.TransientError` / `PermanentError` subclasses, so
  `autoretry_for=(TransientError,)` on your Celery tasks catches them with no
  special-casing for where the failure came from.

Import as `from api.llm import structured_call` (cross-package — absolute,
per `api/AGENTS.md`).

### `LLMPurpose` (from `api.contracts.enums`, unchanged from the freeze)

`CHAPTER_CLASSIFY`, `CHARACTER_EXTRACT`, `RELATION_EXTRACT`, `ADJUDICATE`,
`ANSWER`, `JUDGE`. `JUDGE` always routes to a frontier model and raises
`PermanentLLMError` outright if `settings.inference_mode == LOCAL` or no
`settings.frontier_model` is configured — it never silently downgrades to the
local model.

### `plan_batches` — the Sprint 3 dependency, ready now

```python
def plan_batches(
    items: Sequence[T],
    *,
    prompt_tokens: int,
    text_of: Callable[[T], str],
    max_context: int,
    output_reserve: int,
    safety_margin: float = 0.9,
    tokenizer_model: str | None = None,   # defaults to settings.llm_model
) -> list[BatchPlan[T]]
```

- Counts with the real model tokenizer (`transformers.AutoTokenizer`,
  `settings.llm_model` = `Qwen/Qwen3-8B-AWQ`), not a chars/4 estimate.
- Packs items greedily, in input order, into `BatchPlan`s that each fit
  `TokenBudget.item_budget` (`api.contracts.llm.TokenBudget` — already
  frozen).
- An item too large to fit the per-item budget on its own is **split on
  token boundaries**, never dropped: each piece becomes its own
  `BatchPlan(items=[piece_text], was_split=True)`. Split pieces come back as
  `str`, decoded from the token slice — if you batch anything other than raw
  text, treat a `was_split=True` plan's items as text you feed to the model
  directly rather than the original item type.
- No hidden global state: pass `tokenizer_model=` if you ever need a
  different model's tokenizer than the one `structured_call` will use for
  the same purpose (you shouldn't need to — they're the same model unless
  `purpose=JUDGE`).

Import as `from api.llm import plan_batches`.

### Migration note — `api/pipeline/chunking.py`

`api/llm.py` (the Sprint 1 prototype: global `ChatOpenAI` + Langfuse handler
+ retrieval + LangGraph in one file) is **deleted** as of this commit, per
S2.7. `_classify_chapter_heading` in your `chunking.py` still does
`from ..llm import langfuse_handler, llm` — that import now fails. Your own
comment on that line already calls this out ("S2.3 batches these calls...
moves them behind `api/llm`'s `structured_call`"), so this should already be
on your S2.3 plan; flagging it here so it's not a surprise mid-rebase. New
shape:

```python
from api.llm import structured_call
from api.contracts.enums import LLMPurpose

result = await structured_call(
    _HEADING_PROMPT.format(text=text),
    ChapterInfoStructuredOutput,
    purpose=LLMPurpose.CHAPTER_CLASSIFY,
    book_id=str(book_id),
    stage="segment_chapters",
)
```

Note `_classify_chapter_heading` is currently sync (`structured_llm.invoke`);
`structured_call` is async throughout (`api/AGENTS.md` — everything that
touches I/O is async), so the call site needs `await` and an async caller.

### What is *not* covered by a live test in this worktree

No vLLM runs in this dev environment (single shared GPU per BRANCH.md §9,
and no `vllm` container in the compose stack as configured for worktree
dev). `structured_call`'s retry-on-`ValidationError` and
connection-failure-vs-4xx classification are covered with the chat model
stubbed at the `api.llm` boundary (`api/tests/llm/test_structured.py`,
`test_errors.py`) — the logic under test is ours, not vLLM's. The brief's
literal acceptance criteria ("forced schema violation retries and succeeds
against vLLM", "killing vLLM mid-call") need to be re-verified once against
a live vLLM during integration; nothing here should be taken as having
proven that end-to-end.

`plan_batches` **is** verified against the real `Qwen/Qwen3-8B-AWQ`
tokenizer (offline, from the shared HF cache) — that part has no vLLM
dependency.

---

## Open item — S2.10 reranker needs a settings key not yet frozen

`RERANKER_ENABLED` (default off) doesn't exist in `api/config/settings.py`
yet, and that file is orchestrator-owned as of the Sprint 2 freeze
(`api/pyproject.toml` joined the frozen list per BRANCH.md §2/SCR-3;
`settings.py` was already on it). Filed as SCR-5 in `plans/sprint-2/SCR.md`
(renumbered at the merge train from SCR-2, which collided with do1's own
retroactive boto3 SCR-2 above, filed independently from the same base).
Non-blocking for be1's Day-4 dependency above; blocking for S2.10's
acceptance criterion. Orchestrator: please land at the next freeze or
sooner if S2.10 needs to ship this sprint.

---

## be1 → fe1 · the page-span coordinate contract (S2.6)

`GET /api/books/{id}/pages/{n}` → `PageRenderOut` is implemented
(`api/pipeline/render.py`). The coordinate space, frozen in `contracts/api.py`'s
`SpanBox` docstring, is:

**PDF user space, origin top-left, unscaled** — i.e. **PDF points** (1/72
inch), not the pixel space of the rendered PNG.

```jsonc
{
  "book_id": "…",
  "page": 12,
  "image_url": "http://…/traverse-be1/books/{id}/pages/12.png?X-Amz-…",  // presigned, 5 min TTL
  "width": 612.0,     // page width in PDF points (e.g. 612×792 = US Letter)
  "height": 792.0,    // page height in PDF points
  "spans": [
    { "page": 12, "x": 72.5, "y": 83.9, "width": 262.0, "height": 10.5 }
    // one per pdfium "text rect" (roughly a line), in document order
  ]
}
```

**What fe1 needs to do to overlay a span on the rendered image:** the PNG is
rendered at 150 DPI, so it is `width * 150/72` pixels wide (e.g. a 612pt-wide
page renders to a 1275px PNG). To draw a span box on top of the image at any
zoom level:

```
scale = renderedImageWidthPx / pageWidthPts   // 150/72 at 100%, adjust by your own zoom factor on top
pixelX = span.x * scale
pixelY = span.y * scale
pixelW = span.width * scale
pixelH = span.height * scale
```

`span.y` is already flipped to top-left origin server-side (pdfium itself
returns bottom-left-origin rects; `render._render_sync` converts once via
`y = page_height - top` so no consumer has to). **No `text` field on
`SpanBox`** — the contract is frozen from the Sprint 1 freeze and only carries
boxes. If Sprint 6's citation highlighting needs to match a quote to a
specific span rather than just drawing every box, that is a new field and
needs an SCR against `contracts/api.py`; nothing here does that matching yet.

Caching: first request for a page is a cold render (fetches the whole source
PDF, ~<2s target); every subsequent request for that page — from any
book/session — hits the MinIO-cached PNG + JSON sidecar and does not touch
the source PDF at all (~<200ms target, verified against the 3-page fixture in
`api/tests/pipeline/test_render.py::TestRenderPageModule::test_a_cached_render_does_not_touch_the_source_pdf`).
Real numbers against a 430-page novel are an integration-time measurement,
not a worktree one (BRANCH.md §9) — nobody should quote a timing claim from
this worktree as the sprint's answer.

`404` if the book doesn't exist, has no stored source, or the page number is
out of range (checked against `book.page_count` when known, otherwise against
the PDF's own page count on the fly).

---

## be1 → be2 · chunk/chapter query shapes for Sprint 4 pass-2 batching

Everything below is in `api/pipeline/repository.py` — `from api.pipeline
import repository`, cross-package per `api/AGENTS.md`. This extends (does not
replace) the repository summary already in `plans/sprint-1/HANDOFF.md`.

### Reading chunks for extraction

```python
async def list_chunks(session, book_id, *, limit=50, offset=0) -> list[DocumentChunk]
```

Returns the **raw ORM row**, not the HTTP contract — `text_embedding` is
included (a normalised unit vector once `pipeline.embed_chunks` has run, else
`None`), which `list_chunks_out` deliberately drops before it reaches the
client. Pass-2 batching should read from `list_chunks`, not from the HTTP
route, if it wants embeddings or wants to avoid the N+1 `Chapter.number` join
`list_chunks_out` does for display purposes.

`DocumentChunk` carries `pages: list[int]`, `page_start`, `page_end`,
`chapter_id` (a real FK, `None` until `assign_chunk_chapters` has run for that
book — see below), `token_count`, `tsv` (generated column, BM25 arm — be2's
S2.9 hybrid retrieval already knows about this from the Sprint 1 freeze).

```python
async def list_chunks_needing_embedding(session, book_id) -> list[DocumentChunk]
```

Exists for `pipeline.embed_chunks`'s own resumability (`WHERE text_embedding
IS NULL`); useful if be2 ever needs to check "has this book finished
embedding" without re-deriving it from stage status.

### Chapters — unchanged shape, now actually populated

`list_chapters`, `upsert_chapters`, `chapter_ids_by_number`,
`chapter_page_ranges` (documented in `plans/sprint-1/HANDOFF.md`) are no
longer stubs — `pipeline.segment_chapters` populates real `Chapter` rows with
`page_start`/`page_end`/`detection_method`/`confidence` for every book that
finishes that stage. **`Chapter.human_verified`** (migration `0007`, SCR-1)
is enforced at the repository layer: `upsert_chapters` never overwrites a
verified row's `title`, even when re-segmentation runs and the detector
reports a different title for the same chapter number
(`api/tests/pipeline/test_failures.py::TestHumanVerifiedChaptersSurviveReprocessing`).
Nothing be2 needs to do differently — just don't write to `Chapter` directly
and bypass this.

### Ingestion status — `book.status` is not authoritative

```python
async def get_stage_statuses(session, book_id) -> list[StageStatus]
def derive_book_status(statuses: list[StageStatus]) -> BookStatus   # pure
```

**Nothing currently updates the `book.status` column as stages run or fail**
— only `POST /reprocess` sets it (to `PROCESSING`, optimistically, before
dispatching). `GET /books/{id}/status` derives the reported status from stage
state via `derive_book_status` rather than reading the column, specifically
so a dead-lettered book reports `FAILED` instead of `QUEUED` forever. If be2's
`relations.extract` or anything else needs to gate on "has ingestion actually
finished for this book," call `get_stage_statuses` +
`derive_book_status`/`get_latest_run`, not `book.status` directly — the
column will lie. Flagged here rather than filed as an SCR because fixing it
properly (a status-transition hook stages call into) is bigger than this
sprint's scope for either of us; worth a Sprint 3 story if it starts causing
real confusion.

---

## be1 → orchestrator · `api/pipeline/storage.py` stopgap, still standing

`ObjectStore` (streaming `put_stream`/`get_object`, plus this sprint's
`put_bytes`/`get_bytes` for small payloads, `presigned_get`, `exists`,
`delete_prefix`) is still a stopgap for `api/ops/storage.py` (do1, not yet
landed in this worktree per its own docstring). Every S2 story that touches
object storage — upload, parse-and-chunk's fetch, and now the page-render
cache — imports `from .storage import store`. Swapping to `api.ops.storage`
once it exists should be a one-line import change at each call site (same
four original names; `put_bytes`/`get_bytes` are new this sprint and do1
should carry them over too, or the page-render cache breaks).

---

## be1 → orchestrator / do1 · S2.3's hand-labelled accuracy number is blocked on a real corpus

The sprint plan's S2.3 acceptance criterion (≥95% chapter-boundary recall,
≤2% false positives against `api/tests/fixtures/chapter_truth/*.json`, hand
labelled against "the seeded corpus") cannot be produced from this worktree:
**no `chapter_truth/` fixtures exist yet**, and the only PDF fixture present
is the synthetic 3-page `three_page_novel.pdf` used for unit tests — there is
no real, multi-chapter public-domain novel to hand-label against. Real corpus
seeding is do1's S2.16, not yet landed here either.

What **is** covered from this worktree: extensive unit-level coverage of the
chapter-detection logic itself (`api/tests/pipeline/test_chunking.py`,
`test_chunking_document.py`) — the three fixed defects (heading-not-first-on
page, text-equality collision, per-heading LLM calls) each have a regression
test. The percentage acceptance number is a Day 5 integration-time
measurement once a real seeded corpus exists, not something this worktree can
honestly report — any number produced against 3 synthetic pages would not
mean anything, and BRANCH.md §9 already warns against reporting performance
numbers taken from a worktree as the sprint's answer. Recommend this becomes
an explicit Day 5 checklist item run against do1's seeded corpus rather than
staying an implicit be1 DoD box.

---

## be1 → orchestrator · full ingestion wall-clock (sprint README DoD)

Same shape of issue as above: "full ingestion unattended on the seeded
corpus, wall clock recorded" needs a real 430-page-scale novel and the shared
GPU/vLLM path, neither of which exist in an isolated worktree
(`EMBEDDING_DEVICE=cpu` here per BRANCH.md §9). All six pipeline stages
(`parse_and_chunk`, `segment_chapters`, `embed_chunks`, plus retry/dead-letter/
resume and now page render) are implemented and covered by the 214-test
worktree suite, but the wall-clock number belongs to the Day 5 integration
run against the real stack, not this worktree.

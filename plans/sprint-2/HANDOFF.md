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

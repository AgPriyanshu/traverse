# Sprint 9 — Handoff notes

## be1 — S9.8 Upload privacy (ETH-2)

**What landed:** `api/pipeline/session_privacy.py` — per-session upload
isolation and real deletion, wired into every route in `api/routes/books.py`.
Summary (full detail in `.agents/skills/codebase-memory/ingestion-pipeline.md`
§"Upload privacy"):

- `POST /projects` links the new project 1:1 to the caller's `UploadSession`
  (migration 0012); the response returns the session token in an
  `X-Session-Token` header (minted fresh if the caller sent none).
- Every book- and project-scoped route enforces ownership: a project with a
  live `UploadSession` 404s for anyone but the matching token; a project with
  no owning session (the seeded public corpus) stays open to everyone,
  unchanged from before this story.
- `content_hash`'s uniqueness is install-wide (frozen schema) but reuse is
  now project-scoped — a duplicate upload against a *different* project is a
  `409`, never silently pooled into someone else's project.
- `DELETE /books/{id}` is real: Postgres cascade (raw `DELETE`, not
  `session.delete()` — see the map for why), MinIO prefix delete, a
  best-effort Langfuse trace purge, and a call into be2's
  `api.graph.cascade.remove_book` / `api.graph.projection.reset_project` for
  the Neo4j side. Project + its `UploadSession` are deleted too once its last
  book is gone.
- 24h TTL sweep: `pipeline.sweep_expired_upload_sessions` is a registered
  Celery task with a `celery_app.conf.beat_schedule` entry set from
  `api/pipeline/tasks.py` (be1-owned; never edited `api/tasks.py` or
  `docker-compose.yml`).

**Two things the next steps need, for do1 / integration:**

1. **No `celery beat` service exists in `docker-compose.yml` yet.** The sweep
   task and its schedule entry are real and unit-tested, but nothing invokes
   Celery's beat scheduler in this compose file today, so the entry is inert
   until one is added — a one-line service (`celery -A api.workers.app beat`)
   sharing the existing worker's image/env. Alternatively, a cron-style
   trigger from `scripts/**` calling `celery_app.send_task("pipeline.sweep_expired_upload_sessions")`
   works without a beat process at all. Either is do1's call (docker-compose.yml
   and scripts/** are do1-owned).
2. **Live-Neo4j verification of the delete cascade is still owed at
   integration.** be1's own test suite (`api/tests/pipeline/test_session_privacy.py`)
   monkeypatches `api.graph.cascade.remove_book` / `api.graph.projection.reset_project`
   rather than calling them for real, per BRANCH.md §4/§9 (be2 has exclusive
   write access to the single shared Neo4j instance during a sprint; be1
   never touches it). The wiring is correct and exercised (the mocks assert
   the right ids are passed), but nobody has yet deleted a book against the
   *live* shared Neo4j and confirmed zero nodes/edges survive. Worth one pass
   during the merge train's integration run.

**A pre-existing conflict this story surfaced and fixed in the same commit:**
`api/pipeline/repository.py::create_book`'s idempotent-reingest fallback
(`get_book_by_hash`) looked up an existing book by content hash **globally**,
with no project scoping at all — a demo session uploading a file whose hash
happened to match *any* existing book anywhere (another private session's, or
the public corpus) was silently handed back that book's id and never got its
own book in its own project. This predates S9.8 (it's the same code path
`F1.5`'s idempotent re-ingest has used since Sprint 1) but is exactly the kind
of pooling ETH-2 exists to rule out, so it's fixed here rather than filed as a
gap: the fallback is now `get_book_by_hash_in_project`, and a genuine
cross-project collision surfaces as `IntegrityError` → `409`, not a reuse.

## be1 — S9.9 OCR path (§3.2) — formally deferred

**Decision: deferred, not built.** Checked what exists: `DocumentChunker`
takes an `ocr: bool = False` flag straight through to Docling's
`DocumentConverter(do_ocr=ocr)` (`api/pipeline/chunking.py`) — that is the
entire footprint. No text-density check, no automatic routing between the
digital and OCR paths, no scanned-PDF fixture, no page-provenance-survives-OCR
verification, no quality measurement. This has been the state since Sprint 2
(see `.agents/skills/codebase-memory/ingestion-pipeline.md`'s existing OCR
gotcha) and Sprint 8's retro (`plans/sprint-8/RETRO.md`) does not list OCR
among what it left room for — its carried-over items are a frontier judge key,
an extraction-mode switch, and ablation metric wiring, none of which touch
this.

**Why not built this sprint:** two structural blockers, not just time:

1. **RapidOCR's weights are not in the offline model cache.** The existing
   map already documents that RapidOCR downloads from `modelscope.cn` outside
   the HF cache the moment `ocr=True` is exercised — `make warm-models` never
   pre-warmed it, so a real OCR test run would violate the
   `MODELS_OFFLINE=1` / no-network testing contract (AGENTS.md) the whole
   suite depends on. Building the routing logic without ever being able to
   run it against real OCR output would be exactly the kind of code that
   "looks complete and is not" the sprint brief warned about for S9.8's
   deletion path — the same standard applies here.
2. **No scanned-PDF fixture exists**, and the corpus is digitally-typeset
   novels by design (public-domain, already-digital sources) — building one
   deliberately-scanned fixture plus a measured quality delta (what the
   conditional build asked for) is its own scoped piece of work, not a
   same-sprint add-on to S9.8's substantially larger privacy/deletion story.

**What this means for S9.9's own DoD line** ("OCR either working with
measured quality, or formally deferred in writing"): deferred in writing,
here and in `plans/BACKLOG.md`'s deferred-items table (updated in this
commit — see the row's new "Revisit" note).

**To actually build this in a future sprint:** (a) pre-warm RapidOCR's
weights into the shared model cache alongside Docling/BGE-M3 (do1's
`make warm-models`), (b) add one deliberately-scanned fixture PDF, (c) add a
text-density check in `DocumentChunker.load_document` (e.g. extracted
chars-per-page below a threshold) that re-converts with `ocr=True`, (d)
verify `chunk.meta.doc_items[*].prov[*].page_no` still resolves through
Docling's OCR backend the same way it does today for the digital text layer —
this is the one part of the whole feature that is genuinely risky, since the
existing map already flags provenance as "the whole product promise."

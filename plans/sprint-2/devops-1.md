# Sprint 2 · DevOps Engineer 1

**Branch:** `ai/do1/sprint-2-corpus` · **Worktree:** `../traverse-wt/do1`

## Mission

Storage, the corpus, and observability. By Friday anyone can run `make seed` and
have five licensed public-domain novels staged locally, every pipeline stage is
traced with timing and token cost, and the integration test that gates the merge
train runs a real book end to end in CI.

## Owned paths

`docker/**`, `docker-compose*.yml`, `scripts/**`, `.github/workflows/**`,
`api/ops/**`, `Makefile`, `.env.example`

---

## S2.15 — MinIO

Buckets per BRANCH.md §4. Presigned GET for page renders (be1's S2.6) with a
15-minute TTL — the URL reaches the browser, so it must not be permanent.
Lifecycle rule expiring `books/*/pages/*` after 30 days; they regenerate on
demand and a cache is not a database.

Provide `api/ops/storage.py`: `put_stream`, `presigned_get`, `exists`,
`delete_prefix`. be1 imports it. `delete_prefix` is ETH-2's deletion primitive —
build it now.

*Acceptance:* 200 MB streaming upload holds flat memory. Presigned URL works
from the browser and 403s after expiry.

## S2.16 — Corpus seeding

`scripts/seed_corpus.py` fetching the PRD §7 public-domain set from Project
Gutenberg / Standard Ebooks:

| Title | Why (PRD §7) |
|---|---|
| Pride and Prejudice | dense, checkable family network; the aggregation test |
| Wuthering Heights | **the name-collision regression case** |
| Frankenstein | nested framing → assertion provenance |
| The Great Gatsby | first-person narrator who is a character |
| Anna Karenina | scale + patronymics/diminutives stress case |

Where only EPUB/HTML exists, convert to PDF **with stable pagination** and
record the conversion in a manifest — citations reference page numbers, so a
regenerated corpus with different pagination invalidates every labelled eval
answer from Sprint 8. Pin the manifest with source URL, licence, SHA-256, page
count, and conversion command.

`make seed` is idempotent, resumable, and checksum-verified. Write
`corpus/LICENSES.md` — this is ETH-1 evidence and it belongs in the public repo.

*Acceptance:* `make seed` on a clean machine produces five PDFs with matching
checksums. Re-running downloads nothing.

## S2.17 — Observability

- **Langfuse per stage.** Every ingestion run is one trace; every stage a span;
  every LLM call a generation nested under its stage. A run is then one link in
  the dead-letter view.
- `api/ops/metrics.py` — decorator recording stage name, book, wall clock, rows
  written, tokens in/out, estimated cost, into `ingestion_stage`. This table is
  where Sprint 9's F7.1 dashboard reads from, so define the columns now with be1.
- Cost table in config: per-model input/output USD per 1M tokens, local model
  costed at amortised GPU-hours so the local-vs-API comparison is honest rather
  than "local is free".

*Acceptance:* One ingestion produces one Langfuse trace with every stage and
every LLM call nested correctly, and `ingestion_stage` totals match it.

## S2.18 — Monitoring and CI

- **Flower** on the `dev` profile for queue depth and task inspection.
- **Dead-letter**: `GET /api/ops/pipeline/dead-letter` listing failed runs with
  stage, error, attempts, and the Langfuse trace URL.
- **`make test-integration`** — the merge-train gate: bring up the `ci` profile,
  ingest a **20-page fixture novel** (not a real one; CI must not take 25
  minutes), assert chunks with page provenance, chapters detected, embeddings
  present, then tear down. Target under 8 minutes.
- Nightly full-corpus ingestion on the GPU host, posting wall clock and cost to
  the run summary. This is the number PRD NFR-perf (≤25 min / 350pp) is judged
  on, and it needs a trend line from Sprint 2, not a measurement in Sprint 9.

*Acceptance:* `make test-integration` green on a clean checkout and wired into
the merge train.

---

## DoD

- [ ] `make seed` reproducible with a checksummed, licensed manifest
- [ ] Every stage traced; cost and timing recorded per run
- [ ] Integration test gating the merge train, under 8 minutes
- [ ] Nightly trend job reporting ingestion wall clock
- [ ] `HANDOFF.md`: `api/ops/storage.py` and `metrics.py` signatures for be1

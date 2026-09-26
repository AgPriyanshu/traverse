# Sprint 5 handoff — do1

## S5.13 — Series corpus

`scripts/seed_corpus.py`'s `CorpusBook` gained series fields (`series_key`,
`project_name`, `project_kind`, `series_order`, `canonical_series_number`).
`SERIES_CORPUS` holds two series, both fetched, paginated and checksummed for
real (this is not a stub — `corpus/manifest.json` and `corpus/LICENSES.md`
are committed with live SHA-256s from the real gutenberg.org fetch):

| Project | Books | Notes |
|---|---|---|
| Anne of Green Gables | 6 of 8 | see below |
| Sherlock Holmes | 4 (novels) | A Study in Scarlet, The Sign of the Four, The Hound of the Baskervilles, The Valley of Fear |

**The sprint brief's premise that "Project Gutenberg has all 8 [Anne] books"
does not hold for gutenberg.org.** Verified directly against the live
catalog rather than assumed: "Anne of Windy Poplars" (1936, the real book 4)
and "Anne of Ingleside" (1939, the real book 6) are still under US copyright
(95 years from publication — until 2031 and 2034) and are not distributed by
the US Project Gutenberg. They exist on gutenberg.net.au under Australian
copyright law (life+70), a different licence regime this corpus deliberately
does not mix in alongside the US-PD Gutenberg License the rest of
`corpus/LICENSES.md` documents. Six books ship instead, `series_order` 1-6
with no gap; each book's true position in the eight-book series is carried
as `canonical_series_number` in `corpus/manifest.json` for documentation.
This does not affect S5.14's gold set (only books 1-3 are labelled) or the
sprint's demo script (only books 1-3 are uploaded).

`make seed` is unchanged — still just the original standalone five, same
runtime budget as before. `make seed --all` (or `--only <series keys>`)
builds the series corpus too. `make seed-series` (new) creates both
projects (`kind=SERIES`) directly in Postgres — `POST /projects` is still
S5.9 (fe1), so this follows the exact precedent `scripts/ingest_book.py`
already set for the standalone project — and uploads each series' books
through the real `POST /projects/{id}/books?series_order=N` in order,
sequentially, idempotent on re-run.

## S5.14 — Reconciliation eval

*(added once implemented — see below)*

## S5.15 — Multi-book orchestration

*(added once implemented — see below)*

## Known carried infra items (spot-checked, not re-investigated)

- **Test/live MinIO bucket isolation** (SCR-19, Sprint 4): `docker-compose.yml`'s
  `test` service still overrides `MINIO_BUCKET: ${TEST_MINIO_BUCKET:-traverse-test}`,
  `.env.example` still lists `traverse-test` in `MINIO_BUCKETS`, and
  `docker/minio/init-buckets.sh`'s fallback default still includes it. Still
  in place.
- **Per-worktree test image tag** (A-3.2): `Makefile`'s
  `export TEST_IMAGE_TAG ?= $(notdir $(CURDIR))` and
  `docker-compose.yml`'s `image: traverse-api-test:${TEST_IMAGE_TAG:-...}`
  are both still there. Still in place.

## For the orchestrator / be1

See `plans/sprint-5/SCR.md` SCR-1 — do1 cannot implement the per-project
reconcile advisory lock itself (`api/pipeline/**` is be1-owned), but S5.15's
acceptance criterion depends on it existing. Flagged rather than silently
assumed.

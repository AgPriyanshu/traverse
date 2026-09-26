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

`eval/schema/identity.schema.json` + `eval/gold/anne_of_green_gables/
identity.yaml`: 13 hand-labelled characters across Anne of Green Gables books
1-3, checksum-pinned per book like `roster.schema.json`/`relations.schema.json`
but multi-book (its own `books` list, one `pdf_sha256`/`page_count` pin per
book). Deliberately includes the cases that matter: Anne's own alias
narrowing, a death (Matthew Cuthbert, book 1 — the primary cross-book
blocking case), a present/present/absent gap appearance (Miss Josephine
Barry), a death near the end of the window (Ruby Gillis, book 3), and three
characters new only in book 3 with no earlier history.

`eval/identity_metrics.py` (pure, unit-tested against a hand-worked toy
example the same way `eval/metrics.py`'s B³ implementation is):
`score_identity_links` (pair-level link precision/recall, false-merge rate,
duplicate rate), `block_precision`, `canonical_graph_checksum`
(order-independent — sorts before hashing, verified by a test that permutes
input order and checks the hash is unchanged).

`api/ops/reconciliation_quality.py` (new do1-owned adapter) reads real
`Character`/`CharacterAppearance`/`Relation` rows for a project, matches each
book's appearances against gold **per book**, not project-wide — a
project-wide match would force one greedy mapping and hide exactly the
failures this eval exists to catch (one gold person split across two
predicted `Character` rows across books = a duplicate; one predicted row
matching two different gold people in two different books = a false merge).
Behind two new routes: `GET /ops/reconciliation-quality?project_id=` and
`GET /ops/reconciliation-order-check?project_id=&compare_project_id=` (the
order-independence hard gate — see SCR-1 for the frozen route-count test
this bumps). `eval/runners/reconciliation.py` + `make eval-reconciliation
PROJECT=<slug>` renders the markdown table; false-merge rate above 1% is a
hard failure (exit 1), never folded into an F1. `.github/workflows/
reconciliation-quality.yml`: a PR-scoped job (books 1-3 only, to bound CI
cost) plus a nightly `order-independence` job that ingests forward and
reverse into two projects and compares checksums.

**Unverified end to end, by design, same situation S3.14 was in before be1's
pass-1 merged:** `pipeline.reconcile_characters` is still
`raise NotImplementedError(...)` in this worktree (`api/pipeline/tasks.py`,
S5.1/S5.2, be1's story, developed in parallel in a separate worktree not yet
merged to `ai-master`). Every function above is real and unit-tested against
synthetic data; what is not yet checked is the live number this produces
against the real Anne corpus, because the stage the number depends on does
not exist in this branch's history yet. It will start reporting real numbers
the moment be1's reconcile lands and re-runs through `make seed-series` +
`make eval-reconciliation` — no code change needed here, matching the
`extraction-quality.yml` precedent from Sprint 3.

One finding worth flagging early: `Character` is already unique on
`(project_id, canonical_name)` (migration 0006, Sprint 3), and Sprint 4's
retro (finding 7) says `resolve_aliases` already upserts by that key. That
means a **naive** baseline — two books whose pass-1 canonicalizes the same
surface form to the exact same string — may already partially link across
books today, before S5.1/S5.2's smarter cascade lands, which is worth
checking first rather than assuming today's number is zero.

## S5.15 — Multi-book orchestration

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

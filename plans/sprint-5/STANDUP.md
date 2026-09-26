# Sprint 5 standup — do1

## 2026-09-26

**Landed:** S5.13 (series corpus). Extended `scripts/seed_corpus.py` with
series metadata and a `SERIES_CORPUS` list; fetched, licensed and paginated
Anne of Green Gables (6 of 8 books — see HANDOFF.md for why 4 and 6 are
missing) and the four Sherlock Holmes novels, checksums pinned in
`corpus/manifest.json`. `scripts/seed_series.py` + `make seed-series` creates
both series projects and queues their books in order.

**Next:** S5.14 (reconciliation eval — cross-book identity gold set, link
P/R, false-merge rate), then S5.15 (multi-book orchestration).

**Blocked:** nothing yet.

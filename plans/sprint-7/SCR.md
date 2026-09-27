# Sprint 7 — Schema/shared-file change requests

### SCR-1 · do1 · 2026-09-27
**Need:** `api/tests/pipeline/test_books_routes.py:392`'s frozen
`len(response.json()["paths"]) == 43` assertion needs bumping to `45`.
**Why:** S7.11 added two new do1-owned routes to `api/routes/ops.py` —
`GET /ops/review-metrics` and `GET /ops/review-alerts`. Same class of
collision as S3.14/S3.15 (do1's SCR-2/SCR-3, `1dee51b`): any new route bumps
this count, and the file asserting it is be1-owned
(`api/tests/pipeline/**`), so do1 cannot fix it directly.
**Blocking:** no — informational only, per `infra-topology.md`'s documented
gotcha ("not a regression to chase ... check whether an SCR already covers
the new count"). Not fixing it will fail `test_books_routes.py` at the merge
train until whoever owns that file bumps the literal.
**Proposed:** change `== 43` to `== 45` in
`api/tests/pipeline/test_books_routes.py`.

# Sprint 8 — Schema/Shared-File Change Requests

### SCR-1 · do1 · 2026-09-28
**Need:** `api/tests/pipeline/test_books_routes.py`'s frozen
`len(response.json()["paths"]) == 45` assertion needs bumping to `47`.
**Why:** S8.8 added two new do1-owned routes to `api/routes/ops.py` —
`GET /ops/eval-runs/latest` and `GET /ops/eval-runs/{run_id}` (reading back
the ablation runs `scripts/run_ablation.py` writes). Same class of collision
as S3.14/S3.15 (SCR-2/SCR-3) and S7.11 (SCR-2, `1dee51b`): any new route
bumps this count, and the file asserting it is be1-owned
(`api/tests/pipeline/**`), so do1 cannot fix it directly.
**Blocking:** no — informational only, per `infra-topology.md`'s documented
gotcha ("not a regression to chase ... check whether an SCR already covers
the new count"). Not fixing it will fail `test_books_routes.py` at the merge
train until whoever owns that file bumps the literal.
**Proposed:** change `== 45` to `== 47` in
`api/tests/pipeline/test_books_routes.py`.

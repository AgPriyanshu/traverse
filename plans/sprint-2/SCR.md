# Sprint 2 — Schema & Contract Change Requests

Carried in from Sprint 1. Non-blocking requests batch into the Day-1 freeze.

### SCR-1 · be2 · carried from Sprint 1 · ACCEPTED for the Sprint 2 freeze

**Need:** `GraphEdgeOut.page_refs` is `list[int]` and carries no book dimension.

**Why:** relations are project-scoped, so an edge's evidence can come from more
than one volume. `page_refs: [47, 214]` cannot say which book either page is in
— and in a series a citation without its book is not a citation. This is the
only citation surface in the contracts with that hole. The Neo4j projection
already stores `"<book_order>:<page>"`, so the read path currently discards the
book on the way out.

**Blocking:** no. Bites at Sprint 5 (series) at the latest, and the frozen
contract is what fe1 generates its client from, so it moves at a freeze rather
than mid-sprint.

**Proposed:** a `PageRefOut {book_id, series_order, page}` struct, used by
`GraphEdgeOut.page_refs` and anywhere else a bare page number is returned.
Orchestrator lands it in migration/contract freeze for Sprint 2.

### SCR-2 · do1 · 2026-09-19 · retroactively filed

**Need:** `boto3` (S2.15, `api/ops/storage.py`'s MinIO client) is not in
`api/pyproject.toml`.

**Why:** `api/pyproject.toml` became orchestrator-owned at the Sprint 2 freeze
(BRANCH.md, "`api/pyproject.toml` joined this list at the Sprint 2 freeze").
`api/ops/storage.py` needs an S3 client to talk to MinIO and none of the
dependencies already in the project provide one.

**Blocking:** no. Worked around as a stopgap in `api/Dockerfile`'s runtime
stage (`uv pip install boto3` alongside the existing pytest/ruff stopgap) and
in `.github/workflows/ci.yml`'s `test-api` job, so nothing is blocked pending
the freeze — this entry exists so the dependency lands in `uv.lock` properly
next freeze instead of staying a Dockerfile layer forever.

**Proposed:** add `boto3` to `api/pyproject.toml`'s main dependency group at
the Sprint 3 freeze; delete the `uv pip install boto3` stopgap from
`api/Dockerfile` and `ci.yml` in the same commit.

**Retro note:** this SCR should have been filed in the same commit as
`api/ops/storage.py` (S2.15) — its commit message claimed "SCR filed" but
nothing was appended here. Caught and filed late by the next `do1` session;
flagged for the Sprint 2 retro (BRANCH.md: "a memory/process file that drifts
is worse than none, because agents trust it").

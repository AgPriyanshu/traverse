# Sprint 4 — Schema Change Requests

Numbered after checking the sibling worktrees: be1 filed SCR-1 and fe1 filed
SCR-9 to SCR-12, so do1 starts at SCR-13. Renumber at the merge train if
another agent landed one in between.

---

### SCR-13 · do1 · 2026-09-23

**Need:** bump the frozen OpenAPI path count in
`api/tests/pipeline/test_books_routes.py::TestStillFrozen` (be1-owned) by 2.
do1 added `GET /ops/relation-quality` and `GET /ops/relation-cost`
(`api/routes/ops.py`). Same collision as Sprint 3 SCR-3; a subset check would
end the recurring bump.

**Blocking:** the count assertion fails on this branch until bumped.

---

### SCR-14 · do1 · 2026-09-23

**Need:** pass-2 per-run cache and prefilter counters on `IngestionStage` (or
`StageRecord`): `prefix_cached_tokens`, `chunks_seen`, `chunks_skipped`.
`GET /ops/relation-cost` currently derives chunks processed from
`relations.extract`'s `rows_written` (be2 must write the number of chunks sent
to the model there) and reads the prefix-cache hit rate from vLLM's cumulative
counters, which blend every run since the server booted.

**Why:** a per-book cache hit rate is only exact if the stage records its own
window. Interim: the nightly job differences counters where it can
(`api/ops/vllm_metrics.hit_rate_between`).

**Blocking:** no.

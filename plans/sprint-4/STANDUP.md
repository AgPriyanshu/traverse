# Sprint 4 — Standup

## be1

**Landed (branch `ai/be1/sprint-4-scenes`):**
- S4.8 scene segmentation (`api/pipeline/scenes.py`), repository and query
  helpers (`scene_repository.py`), stage wiring at the tail of
  `resolve_aliases` (`scene_stage.py`).
- S4.9 speaker cascade (`speakers.py`): explicit tag, adjacent narration,
  two-party alternation, batched LLM fallback that halves on `LengthLimitError`.
- S4.10 `pass2_candidates` and `prefilter_stats` (`prefilter.py`).

**Blocked:** the scene tables are not in `api/db/models` or any migration
(SCR-1). The stage skips with a warning until they exist. Query shapes for be2
are in `HANDOFF.md`.

**Found:** S3.4 has no co-presence check to back-fill (see `HANDOFF.md`).

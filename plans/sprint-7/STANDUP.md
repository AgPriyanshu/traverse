# Sprint 7 — Standup

## be1 — 2026-09-28

**Landed:** all three of be1's Sprint 7 stories — S7.5 (`human_verified`
guards, repository layer), S7.6 (disagreement raises a task instead of
overwriting), S7.7 (correction feedback store).

Audited every write path in `api/extraction/**`, `api/pipeline/**`,
`api/reconcile/**` that touches `character`, `character_mention`, `chapter`,
`rejected_candidate`. Two guards already existed and were correct
(`persist_characters`, `upsert_chapters`'s never-overwrite, `recompute_derived
_fields`); two real gaps found and closed:

- `replace_candidates` deleted **every** `RejectedCandidate` row for a book
  unconditionally, including one a human had verified — fixed to only clear
  unverified ones, and to never let a verified rejection's surface form
  re-enter `BookCharacterCandidate` on a later run.
- `queue_collision_review`/`queue_cross_book_review` wrote a payload shape
  that predates Sprint 7's contract freeze (`c82a613`) — would have failed
  `ReviewTaskOut` validation the first time `GET /review/tasks` read one back.
  Fixed to the frozen `MergeCharactersPayload`/`MergeAcrossBooksPayload`
  shape, and deduplicated (both sides of one collision used to queue two
  mirror-image tasks; a rerun of an unchanged block used to queue a third).

New shared primitive, `api/pipeline/verification.py`: `raise_disagreement`
(dedup by a stable key, open-or-resolved check, one task per genuine
disagreement) and `record_correction_feedback`/`list_correction_feedback`
(S7.7's store). Wired `raise_disagreement` into chapter re-detection
(`confirm_chapter_split`) and rejected-candidate reclassification
(`classify_candidate`); the collision/cross-book writers above use it too.

One case doesn't fit any of the six frozen `ReviewTaskType` shapes without
misusing one: a verified `Character`'s own `aliases`/`importance_tier`
disagreeing with a same-book rerun has no shape built for "one entity, old
value vs. proposed value". Guarded (never written) and logged; not queued.
Filed as SCR-1, non-blocking — see `plans/sprint-7/SCR.md` and `HANDOFF.md`.

Along the way, fixed a `sqlalchemy.exc.MissingGreenlet` I introduced myself
while building the chapter-disagreement check: reading a verified `Chapter`
ORM object's attributes *after* the commit that expires it (same documented
gotcha as `pipeline/tasks.py`'s `Character` id comment) — fixed by snapshotting
the fields needed before the commit, not touching the live object after.

**Verification:** targeted run — `api/tests/extraction`, `api/tests/pipeline`,
`api/tests/reconcile`, `api/tests/workers` — 353 passed, no regressions.
`ruff check`/`ruff format --check` clean on every changed file. One
pre-existing test's assertion updated to match the corrected payload shape
(`test_service.py::TestDeathBlocksAutolink`) — its scenario is untouched.

**Next:** none — full sprint-7 scope for be1. SCR-1 is a clean pickup for
whoever's at the next contract freeze if a `confirm_field`-shaped task turns
out to be worth it.

**Blocked:** not blocked.

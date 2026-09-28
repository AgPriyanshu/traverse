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

## fe1 — 2026-09-28

**Landed:** all three stories (S7.8-S7.10) — the keyboard-only review queue,
five task-type renderers, and bulk accept. Regenerated `schema.d.ts`/`types.ts`
against the frozen `ReviewTaskPayload` union first (this sprint's contract
freeze, commit `c82a613`), verified it matched the contract exactly, then built
against it.

Picked this up mid-flight after a rate-limit interruption with uncommitted
work in progress; committed in per-story chunks as instructed rather than one
combined commit, then continued: wrote the timed 50-task keyboard-only
automated verification (`review-speed.test.tsx`) the S7.8 DoD line asks for,
fixed the one regression it and the route change surfaced
(`routes.test.tsx`'s smoke test still expected the old `NotYetBuilt` stub
copy), and wrote `plans/sprint-7/HANDOFF.md`'s decision/payload table for be2 —
`ReviewResolution.decision` is a free `str` in the frozen contract, not an
enum, so the exact vocabulary each renderer sends is this session's design and
needs be2's resolution handlers to match it (or a two-way reconciliation if
they were already written against something else).

**Verification:** `docker compose --profile test run --rm test-web` — 202
Vitest tests passing across 19 files (+9 over the Sprint 6 baseline of 193),
lint and typecheck clean in that same containerized run. `pnpm build`
(`tsc -b && vite build`) clean on the host via an alternate `--outDir` — this
worktree's `dist/` had root-owned files left over from an unrelated earlier
session that a non-root `rm -rf` can't clean up; gitignored, not part of the
diff, noted in HANDOFF.md so nobody else burns time on the same permission
error.

The 50-tasks/8-minutes DoD line is verified as a **mechanical** proxy, not a
literal timed human session (an agent can't run one): `review-speed.test.tsx`
drives 50 mixed-type tasks to zero-open with exactly 50 keystrokes (one
fast-path key per task, no navigation keys — resolving the active task
auto-advances to the next). Measured interaction-loop overhead is ~2.3s for
all 50 resolutions in that test, i.e. the mechanism itself adds negligible
friction against the 480s budget; what actually spends the budget is reading
each task, which is S7.9's job (show everything needed inline) not S7.8's.

**Next:** none outstanding for fe1 in Sprint 7. Re-run the demo path once
be2's S7.1-S7.4 (the LangGraph interrupt flow, resolve handlers) land on
`ai-master`, and cross-check the `decision` vocabulary in HANDOFF.md against
what be2 actually implemented — that's the one place a real mismatch could
hide until integration.

**Blocked:** not blocked. Built and tested against the frozen
`ReviewTaskOut`/`ReviewTaskPayload`/`ReviewResolution` contract with realistic
fixtures; not yet verified against a live be2 backend (S7.1-S7.4 hadn't merged
into this worktree at time of writing), same pattern as every prior sprint's
frontend work here.

Commits on `ai/fe1/sprint-7-queue`:
1. `chore(api): regenerate schema for Sprint 7 review task payloads [S7.9]`
2. `feat(review): five task-type renderers with per-task keyboard decisions [S7.9]`
3. `feat(review): keyboard-only queue with prefetch, optimistic undo, bulk accept [S7.8/S7.10]`
4. `test(review): keyboard flow coverage across all five task types [S7.8/S7.9/S7.10]`
5. `test(review): timed 50-task keyboard-only sweep and fix the route smoke test [S7.8 DoD]`
6. `docs(sprint-7): HANDOFF/STANDUP and the review-queue memory map entry`

# Sprint 7 · Backend Engineer 1

**Branch:** `ai/be1/sprint-7-durability` · **Worktree:** `../traverse-wt/be1`
**Owned:** `api/pipeline/**`, `api/extraction/**`, `api/workers/**`

## Mission

Make human corrections permanent. PRD F5.4 is unambiguous: corrected values are
`human_verified` and **never overwritten by a subsequent automated pass**. A
reviewer who finds their correction gone after a re-run stops reviewing, and the
whole differentiating feature dies with them.

---

**S7.5 `human_verified` guards.** Audit every write path that touches
`character`, `character_mention`, `relation`, `relation_evidence`, `chapter`.
Each must skip or diff against verified records rather than upserting over them.

Enforce it at the **repository layer**, not per call site. A guard that depends
on every future caller remembering is a guard that fails in Sprint 9. Consider a
DB-level trigger as a backstop, and write the test that proves an unguarded write
is rejected.

**S7.6 Disagreement → task, not overwrite (F5.4).** When a re-run produces a
different value for a verified field, do not write it. Create a fresh
`confirm_field`-style task carrying both values, both pieces of evidence, and
what changed since. The human decides; the model does not get a second vote.

*Acceptance:* Re-running full extraction on a reviewed book preserves 100% of
verified values and raises exactly one task per genuine disagreement — not one
per chunk that mentions the field.

**S7.7 Correction feedback store.** Every correction persisted with enough
context to learn from: task type, model value, human value, model confidence,
evidence, resolution method, timestamp.

This is what Sprint 8 calibrates against (PRD F2.2's calibrator). Store the
model's **confidence at decision time** — reconstructing it later is impossible,
and without it the calibration story in Sprint 8 does not exist. If you record
only one thing from this story, record that.

## DoD

- [ ] Guards at the repository layer, with a test proving an unguarded write fails
- [ ] Re-run preserves 100% of verified records — proven on a reviewed novel
- [ ] Disagreements raise one task each, deduplicated
- [ ] Feedback store captures decision-time confidence
- [ ] `HANDOFF.md`: feedback store schema for do1's Sprint 8 calibration

# Sprint 7 · Frontend Engineer 1

**Branch:** `ai/fe1/sprint-7-review` · **Worktree:** `../traverse-wt/fe1`
**Owned:** `web/src/**`, `web/tests/**`

## Design input

Read [design/DESIGN.md](../../design/DESIGN.md); implement the `review-queue`
artboard. The acceptance criterion — **50 tasks in under 8 minutes, no mouse** —
is a design constraint before it is an implementation one. If the artboard needs
a mouse to be usable, file a DCR.

---

**S7.8 The queue (F5.3).** Split view: task list left, active task right. Never a
modal — a modal per task costs an open/close cycle 50 times.

Keyboard map, shown in an on-screen legend and a `?` overlay:

| Key | Action |
|---|---|
| `j` / `k` | next / previous |
| `a` | accept |
| `e` | edit |
| `m` | merge (on `merge_characters`) |
| `s` | keep separate |
| `x` | select for bulk |
| `u` | undo last |
| `?` | shortcuts |

Two things make or break the 8-minute target: **prefetch the next three tasks**
so advancing never waits on a request, and make resolution **optimistic** with
undo rather than blocking on the server. Both are the difference between 8
minutes and 20.

`u` undo is not a nicety — a reviewer moving at speed will mis-key, and without
undo they slow down to avoid it.

Sortable by priority (default), confidence, age, character importance.

**S7.9 Five task renderers (F5.2).** Each built for its decision, not a generic
form:

- `merge_characters` — two columns of mention contexts with pages, aliases,
  first appearance. The reviewer needs to see *why the system is unsure*.
- `confirm_relation` — the proposed edge with every evidence quote and page,
  accept / change predicate / reject.
- `resolve_conflict` — side-by-side contradicting evidence; pick one, or mark it
  a temporal transition (which is often the right answer and must be one key).
- `classify_candidate` — the candidate with contexts; character / place / org /
  not an entity.
- `confirm_chapter_split` — the heading with surrounding page context.

Every page reference clicks through to the viewer without losing queue position.

**S7.10 Bulk accept.** Select a group of high-confidence tasks of one type and
accept together, with a clear count and an undo window. Guard against
accept-all-blind: show the confidence range being accepted and require a
confirm above a task count threshold.

## DoD

- [ ] **50 tasks in under 8 minutes, keyboard only — timed, recorded, in the retro**
- [ ] Next-task prefetch; no visible wait between tasks
- [ ] Optimistic resolution with working undo
- [ ] Every renderer shows enough to decide without leaving the queue
- [ ] Screen-reader usable; focus never lost on task advance

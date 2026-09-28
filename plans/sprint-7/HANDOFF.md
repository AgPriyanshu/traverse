# Sprint 7 — Handoff

## fe1 — S7.8 through S7.10

All three stories built against the frozen `ReviewTaskPayload` union
(`api/contracts/api.py`, Sprint 7 freeze commit `c82a613`) and the generic
`GET /api/review/tasks` / `POST /api/review/tasks/{id}/resolve` endpoints that
already existed in `web/src/lib/api/hooks.ts` from an earlier sprint. Route:
`/books/:id/review` (resolves `project_id` via `useBook`, since review tasks
are project-wide — `merge_across_books` has no single book).

**Files:** `web/src/routes/review/**` (queue engine, five renderers, bulk
accept, shortcuts), `web/src/routes/book/review.tsx` (thin route wrapper),
`web/src/routes/routes.tsx` (wired in, replacing the `NotYetBuilt` stub).

### The decision/payload contract be2 needs to implement against

`ReviewResolution` is `{decision: str, payload: dict[str, Any]}` in the frozen
contract — **`decision` is a free string, not an enum**, so the exact
vocabulary below is this session's design, not something in
`api/contracts/api.py`. be2's resolution handlers (S7.2's brief: "each
resolution handler applies the decision... writes `human_verified`, records to
the feedback store, and resumes the thread") need to switch on these exact
strings per `task_type`. If be2's handlers were already written against a
different vocabulary before this lands, that's a two-way SCR, not a unilateral
change in either direction — please flag rather than silently aliasing.

| `task_type` | `decision` | `payload` | Meaning |
|---|---|---|---|
| `merge_characters` / `merge_across_books` | `"merge"` | `{primary_id: str, merge_ids: list[str]}` | Fold `merge_ids` into `primary_id` — reuse Sprint 3's transactional merge, `primary_id` survives. |
| | `"keep_separate"` | `{}` | Candidates confirmed distinct; no graph change, just resolve the task. |
| `confirm_relation` | `"accept"` | `{}` | Relation confirmed as proposed. |
| | `"change_predicate"` | `{predicate: str}` | Same edge, different predicate (drawn from `GET /api/graph/ontology`). |
| | `"reject"` | `{}` | Relation is wrong; drop it. |
| `resolve_conflict` | `"accept"` | `{relation_id: str}` | This one relation is correct; the other(s) in `conflicting` are superseded/dropped. |
| | `"temporal_transition"` | `{order: list[str]}` (relation ids) | All true, at different times — **the brief's own note that this is often the right answer**, so it's a single key (`t`) in the UI. `order` is the `conflicting` array's own order (whatever the aggregator produced), not reviewer-editable — there's no UI for reordering. If this order isn't actually chronological, that's an aggregator-side concern, not something the review queue can fix without a payload change. |
| `classify_candidate` | `"classify"` | `{kind: CandidateKind}` | One of `person`/`place`/`organisation`/`unknown` (`unknown` = "not an entity" in the UI). |
| `confirm_chapter_split` | `"accept"` | `{}` | Boundary confirmed. |
| | `"reject"` | `{}` | Not a real chapter break. |

Bulk accept (S7.10) sends the **same per-task-type decisions above**, one
`POST /resolve` call per task (no batch endpoint exists or was added) — it
only differs client-side in which tasks it's willing to queue up without a
per-task look: `merge_*` bulks to `keep_separate` (never a blind `merge`,
since picking a primary is exactly the judgment bulk accept can't make
safely), `confirm_relation`/`confirm_chapter_split` bulk to `accept`,
`resolve_conflict` bulks to `temporal_transition`, and `classify_candidate`
only bulks when the task already carries a `kind_guess` (accepts that guess).
See `web/src/routes/review/bulk-decisions.ts`.

**Idempotency dependency (S7.4):** the UI resolves optimistically and delays
the actual `POST` by a 5s undo grace window (see below), so a reviewer who
resolves the same task twice in quick succession (e.g. a slow network retry
racing a second click) is a real scenario, not a hypothetical — confirmed
this is already in be2's S7.4 scope ("resolving an already-resolved task is
idempotent, not an error").

**Two gaps in the payload, not blocking, not filed as SCRs (informational —
neither needs a contract change, both are the queue quietly doing less than
it could):**

- `RelationOut` carries no importance-tier signal, so the "sort by character
  importance" mode (S7.8) only has data for `merge_*` tasks (from the
  `CharacterOut` candidates); `confirm_relation`/`resolve_conflict` tasks sort
  to the back of that mode rather than a fabricated rank. See
  `taskImportanceRank` in `web/src/routes/review/task-meta.ts`.
- `ReviewTaskOut.priority` — assumed **higher number = more urgent, shown
  first** (descending sort). Nothing in the contract states the direction;
  if S7.3's scoring is ascending instead, it's a one-line flip in
  `compareTasks` (`task-meta.ts`), not a rework.

### The queue mechanics (S7.8)

Split view, never a modal. `j`/`k` move; the active task and sort mode are
both URL state (`?task=`, `?sort=`) so a page-reference click-through
(`<PageRef>`) and a browser-back return to exactly the same position — no
app-level store needed, unlike the ask screen's `conversation-store.ts` (there
was no in-flight stream to preserve here, just a cursor).

Resolution is **optimistic with a real undo, not a fake one**: a decision
hides the task and shows an undo toast immediately; the actual `POST` is
deferred behind a `setTimeout` and only fires once 5 seconds pass with no
`u`/"Undo" click. `u` before that window empties the pending timeout and the
task reappears — no request was ever sent, so there's nothing to reconcile
server-side. After the window, `u` has nothing left to undo (the request has
gone out), which is the honest boundary of what a client-only undo can do
without a dedicated `unresolve` endpoint (none exists, none requested).

Prefetch: the next three tasks' first citation page
(`pageRenderQueryOptions`) is warmed via `queryClient.prefetchQuery` on every
move, so a reviewer who follows a citation never waits on that request either.

Per-renderer keyboard handlers are registered through a ref (not React state)
written directly during render (`shortcuts-context.ts` — same
pattern already in this codebase's `use-conversation.ts` for the same reason:
a keystroke inside one renderer's own input, e.g. the predicate `<select>`,
must never re-render the rest of the queue).

**Verification of the 50-tasks/8-minutes acceptance criterion
(`plans/sprint-7/frontend-1.md` DoD):** every task type's fast path is exactly
one key (`m`/`a`/`t`/`a`/`a` for merge/confirm/conflict/classify/split, when
the model's own default is the reviewer's answer), and resolving the active
task auto-advances to the next one — no `j` needed between decisions.
`web/tests/review-speed.test.tsx` drives 50 mixed-type synthetic tasks
end-to-end with exactly 50 keystrokes and zero navigation keys, and asserts
the queue actually empties. This is a mechanical proxy, not the literal timed
human session the DoD line asks for — an agent can't run that — but it is the
part of the claim that regresses silently if someone reintroduces a required
extra keystroke or a blocking round-trip, and it now fails CI if that happens.
Measured interaction-loop overhead in that test is ~2.3s (jsdom, no human) for
all 50 resolutions, i.e. the 8-minute budget is entirely a reading-time budget
against what S7.9's renderers show inline, not a UI-friction one. A literal
timed run against the real backend (once be2's S7.1-S7.4 are live) still
belongs in the retro.

**Verification, full:** `docker compose --profile test run --rm test-web` —
202 Vitest tests passing across 19 files (was 193 at the Sprint 6 handoff;
+9: 8 in `review.test.tsx`, 1 in `review-speed.test.tsx`), lint and typecheck
clean in that same run. `pnpm build` (`tsc -b && vite build`) clean on the
host, checked via an alternate `--outDir` because this worktree's `dist/`
directory had root-owned files left over from an earlier session unrelated to
this work (gitignored, not part of the diff, not fixable without root — noted
here so nobody burns time on the same permission error).

**Not verified against a live be2 backend** — S7.1-S7.4 (the LangGraph
interrupt flow, task types, priority scoring, resolve handlers) were not
merged into this worktree at time of writing. Built and tested against the
frozen `ReviewTaskOut`/`ReviewTaskPayload`/`ReviewResolution` contract with
realistic fixtures, same pattern as every prior sprint's frontend work here.
Re-run the demo once be2's Sprint 7 lands on `ai-master`, and cross-check the
`decision` vocabulary table above against whatever be2 actually implemented.

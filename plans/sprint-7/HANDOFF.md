# Sprint 7 — be2 HANDOFF

## For fe1 (S7.9 — five task renderers)

`GET /review/tasks` returns `list[ReviewTaskOut]`; `ReviewTaskOut.payload` is
the frozen discriminated union in `api/contracts/api.py` ("Sprint 7 (S7.2)"),
keyed on `task_type`:

| `task_type` | Payload | Renderer shape |
| --- | --- | --- |
| `merge_characters` | `MergeCharactersPayload` | side-by-side candidates + contexts |
| `merge_across_books` | `MergeAcrossBooksPayload` | same shape as above (shares `ReviewMergeBase`) — **one renderer, two task types** |
| `confirm_relation` | `ConfirmRelationPayload` | one relation + its evidence + `reason` |
| `resolve_conflict` | `ResolveConflictPayload` | N conflicting relations (currently always 2), evidence keyed by relation id |
| `classify_candidate` | `ClassifyCandidatePayload` | surface form + contexts + a kind guess |
| `confirm_chapter_split` | `ConfirmChapterSplitPayload` | chapter + surrounding text |

That is five renderers over six types, as the freeze note says.

**Priority is live, not static.** `ReviewTaskOut.priority` is recomputed on
every `GET /review/tasks` from current character tiers/mention counts
(`api/review/payloads.py::hydrate`, `api/review/priority.py`) — sort by it,
but do not cache it client-side across requests as if it were stable between
reads.

`POST /review/tasks/{id}/resolve` takes `ReviewResolution {decision: str,
payload: dict}`. **The exact vocabulary below is fe1's** (`ai/fe1/sprint-7-queue`,
`plans/sprint-7/HANDOFF.md` there) — `ReviewResolution.decision` is a free
string in the frozen contract, not an enum, so fe1's S7.8-S7.10 build fixed
the wire vocabulary and `api/review/resolution.py`'s handlers were written
(and, on a first pass, corrected) to match it exactly rather than invent a
second one:

| `task_type` | `decision` | `payload` |
|---|---|---|
| `merge_characters` / `merge_across_books` | `"merge"` | `{primary_id: str, merge_ids: [str]}` — `primary_id` survives, `merge_ids` fold in via Sprint 3's transactional merge |
| | `"keep_separate"` | `{}` |
| `confirm_relation` | `"accept"` | `{}` — sets `human_verified` |
| | `"change_predicate"` | `{predicate: str}` — also recomputes `family` from `graph.ontology.family_of` |
| | `"reject"` | `{}` — deletes the edge (a spurious edge never happened; `ended`/`superseded` both imply it did) |
| `resolve_conflict` | `"accept"` | `{relation_id: str}` — that one relation becomes/stays `ACTIVE` + `human_verified`; the other(s) in `conflicting` become `SUPERSEDED` + `human_verified` |
| | `"temporal_transition"` | `{order: [str]}` (relation ids, earliest first) — chains them: each closes into the next (`status=SUPERSEDED`, `last_book_order`/`last_chapter` set from the successor's `first_*`), the last stays `ACTIVE` |
| `classify_candidate` | `"classify"` | `{kind: CandidateKind}` |
| `confirm_chapter_split` | `"accept"` | `{}` — sets `human_verified` |
| | `"reject"` | `{}` — also sets `human_verified` (the verdict, not a fix); merging/removing the chapter is be1's S7.5/S7.6 territory, `CorrectionFeedback` carries the `"reject"` for it |

An unrecognised `decision` for a given `task_type` raises rather than
silently no-opping — see `resolution.UnknownDecisionError`.

Resolving an already-`resolved` task is safe (idempotent) — the response is
just the task's current state, not an error. Useful if a keyboard-first bulk
flow (S7.8/S7.10) double-fires a request, and confirmed necessary in practice:
fe1's optimistic-resolve-with-undo flow can race a retried `POST` against the
same task.

## For be1

**S7.5/S7.6/S7.7 integration points**, since the two new S7.2 task types with
no trigger site in be2's owned paths are yours:

- `classify_candidate` — call `api.review.queue.queue_classify_candidate(...)`
  from wherever pass-1/rejection decides a candidate is genuinely ambiguous
  between person/place/organisation, rather than constructing a `ReviewTask`
  row directly. It stores the full self-sufficient payload the frontend needs.
- `confirm_chapter_split` — call
  `api.review.queue.queue_confirm_chapter_split(...)` from the chapter
  detection path for a low-confidence split. `Chapter.human_verified` now
  exists (SCR-1 resolved at the freeze); `api/review/resolution.py` sets it
  when the task resolves, but the repository's own never-overwrite guard
  against it is still yours (S7.5).

**`merge_characters`/`merge_across_books` already work end-to-end** —
`extraction/repository.py::queue_collision_review` and
`reconcile/repository.py::queue_cross_book_review`'s existing lean payloads
(`name_a`/`name_b`, `candidate_name`/`target_character_id`) are exactly what
`api/review/payloads.py::hydrate` resolves against current `Character` rows.
No change needed there unless you want to pass `candidate_ids` directly
instead of names (hydration tries that key first, falls back to name lookup).

**A note on ordering, since it affects when your stages actually run:** an
open `merge_characters`/`merge_across_books` task for a book now blocks
`relations.extract`/`relations.aggregate` for *that* book (a real
`interrupt()`, `api/review/workflow.py`, gate `"roster"`) — pass 2 must not
key edges against a roster that might still merge. Your `resolve_aliases` and
`reconcile_characters` stages are unaffected; they queue the task and finish
normally. Resolving the task automatically re-dispatches
`ingestion_chain(book_id, from_stage=EXTRACT_RELATIONS)` (frozen,
`api/tasks.py`) — you do not need to do anything to make the pipeline
continue.

## Schema

No SCR filed this sprint. `Chapter.human_verified`, the `ReviewTaskPayload`
union, and the `review_task`/`correction_feedback` tables were all already
frozen going into Sprint 7 — nothing be2 needed was missing from the freeze.

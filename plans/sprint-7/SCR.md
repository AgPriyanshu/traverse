### SCR-1 · be1 · 2026-09-27T00:00
**Need:** A seventh `ReviewTaskType`/payload shape, e.g. `confirm_field`, carrying
`{entity_type, entity_id, field, verified_value, proposed_value, evidence}`.

**Why:** S7.6 (F5.4) requires that when a rerun disagrees with an already
`human_verified` value, the pipeline raises a review task rather than silently
dropping the write. The guard itself is built and tested
(`api/extraction/repository.py::persist_characters` never overwrites a
verified `Character`'s `aliases`/`importance_tier`), but there is no safe way
to *tell a human about the disagreement* with the six payload shapes frozen at
this sprint's contract freeze:

- `MergeCharactersPayload`/`MergeAcrossBooksPayload` require `candidates:
  list[CharacterOut]` with **two distinct, persisted** characters — the shape
  a resolution handler will reasonably assume means "call the transactional
  merge on these two ids". A single verified character disagreeing with its
  own rerun proposal has only one real id; reusing the type with the same id
  twice risks a handler merging a character into itself.
- `ConfirmRelationPayload`/`ResolveConflictPayload` are typed to `RelationOut`
  — categorically the wrong domain object for a `Character` or `Chapter`
  field.
- `ClassifyCandidatePayload` is pass-1 candidate classification
  (`surface_form`/`kind_guess`), not a correction to an already-persisted,
  already-verified character's fields.

Two adjacent cases in the same story **do** fit an existing shape and are
implemented, not part of this request: a chapter re-detection disagreeing with
a verified `Chapter` uses `confirm_chapter_split` (exact fit — same
`ChapterOut` identity, old vs. proposed described in `preceding_text`/
`following_text`), and a name-collision disagreement uses `merge_characters`
correctly, since both sides genuinely are distinct persisted characters
(fixed in this same change — `queue_collision_review`/`queue_cross_book_review`
previously wrote a payload shape that predates the S7.2 freeze and would have
failed `ReviewTaskOut` validation the first time `GET /review/tasks` read one).

**Blocking:** no — the guard (never overwrite) is the load-bearing half of
F5.4 and is complete and tested without this. This SCR only closes the
"raise a task" half for the single remaining case: a verified `Character`'s
own `aliases`/`importance_tier` disagreeing with a same-book rerun. In the
interim, `persist_characters` logs a warning (`"verified character %s (%s)
disagrees with rerun proposal..."`) so the disagreement is visible in ops
logs even though it does not reach the review queue.

**Proposed:**
```python
class ConfirmFieldPayload(BaseModel):
    task_type: Literal[ReviewTaskType.CONFIRM_FIELD] = ReviewTaskType.CONFIRM_FIELD
    entity_type: Literal["character", "chapter"]
    entity_id: UUID
    field: str
    verified_value: Any
    proposed_value: Any
    evidence: list[MentionOut] = Field(default_factory=list)
```
plus `ReviewTaskType.CONFIRM_FIELD = "confirm_field"` (native Postgres enum —
`ALTER TYPE reviewtasktype ADD VALUE 'confirm_field'`) and a resolution handler
that either writes `proposed_value` over `verified_value` (human overrides
their own prior correction) or dismisses the task (human reaffirms it).

Non-blocking; batch into the next freeze.

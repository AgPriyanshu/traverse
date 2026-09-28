# Sprint 7 — Handoff

## be1 → do1 · `correction_feedback` schema for Sprint 8 calibration (S7.7)

Write side: `api/pipeline/verification.py::record_correction_feedback`. Read
side for the calibrator: `api/pipeline/verification.py::list_correction_feedback`
(optionally scoped by `project_id` and/or `task_type`).

```python
async def record_correction_feedback(
    session, *,
    project_id: UUID,
    task_type: ReviewTaskType,       # which of the six queue types this came from
    model_value: dict[str, Any],     # what the model proposed
    human_value: dict[str, Any],     # what the human decided
    model_confidence: float | None,  # THE MODEL'S CONFIDENCE AT THE MOMENT THE TASK WAS RAISED
    review_task_id: UUID | None = None,
    resolution_method: ResolutionMethod = ResolutionMethod.HUMAN,
    evidence: dict[str, Any] | None = None,
) -> CorrectionFeedback

async def list_correction_feedback(
    session, *, project_id: UUID | None = None, task_type: ReviewTaskType | None = None
) -> list[CorrectionFeedback]
```

`CorrectionFeedback` itself (`api/db/models/review_model.py`, frozen) has
`task_type`, `model_value`/`human_value`/`evidence` (JSONB), `model_confidence`
(float), `resolution_method`, `review_task_id` (nullable FK, `ON DELETE SET
NULL`), `created_at`.

**The one thing to know before you calibrate on this:** `model_confidence` is
whatever the caller passes at the moment they call `record_correction_feedback`
— it is not looked up or recomputed by this function. The intended flow is:
a `raise_disagreement`/task-writing call embeds the model's confidence
somewhere in `ReviewTask.payload` (field name varies by task type —
`ConfirmChapterSplitPayload.confidence`, a `similarity_score` on a merge
payload, etc. — there is no common field across the six frozen shapes), and
be2's S7.2 resolution handler reads it back out of the resolved task's own
payload and passes it through here at resolution time. If a handler ever
calls this with a confidence it invented after the fact (re-running the model,
or defaulting to `None`), the calibration signal for that row is worthless —
this is the one thing S7.7's story text called out as irreplaceable.

This is not yet called anywhere in this codebase: it is a primitive for S7.2's
resolution handlers (be2, `api/review/**`) to call once a human answers a
task. No rows exist until then. `api/tests/pipeline/test_verification.py`
exercises the function directly against a real Postgres so its shape is
proven ahead of that wiring.

`api/tests/conftest.py`'s truncation list now includes `correctionfeedback`.

## be1 → be2 · pre-freeze `ReviewTask` writers now match the frozen contract, and dedup is shared

Two writers predate the S7.2 payload freeze (`c82a613`) and would have failed
`ReviewTaskOut` validation the first time `GET /review/tasks` read one back —
fixed as part of this story's write-path audit, not scope creep:

- `api/extraction/repository.py::queue_collision_review` — now takes
  `character_a_id`/`character_b_id` (both must already be persisted
  `Character` rows) instead of bare name strings, and writes a real
  `MergeCharactersPayload`-shaped payload (`candidates: list[CharacterOut]`,
  `contexts: {}`, `similarity_score: None`, plus `reason`).
- `api/reconcile/repository.py::queue_cross_book_review` — now takes
  `candidate: Character, target: Character` (the caller already had both ORM
  rows in hand) instead of name strings, and writes `MergeAcrossBooksPayload`
  the same way, `similarity_score` set to the match confidence.

Both are deduplicated through a shared helper (below), so if your resolution
handler for `merge_characters`/`merge_across_books` ever calls either of
these again (unlikely, but worth knowing), a second call for the same pair —
open *or already resolved* — is a no-op, not a duplicate row.

**New shared primitive**, `api/pipeline/verification.py::raise_disagreement`:

```python
async def raise_disagreement(
    session, *,
    project_id: UUID,
    book_id: UUID | None,
    task_type: ReviewTaskType,
    dedup_key: str,          # stable across reruns of the SAME disagreement
    payload: dict[str, Any], # already contract-shaped for `task_type`
    priority: int = 1,
) -> ReviewTask | None       # None if a matching task (open or resolved) already exists
```

It stores `dedup_key` inside `payload["dedup_key"]` — Pydantic drops it on the
way out through `ReviewTaskPayload` since none of the six shapes declares it,
so it never reaches a renderer or your resolution handler's typed input; it
only exists for this function's own existence check
(`ReviewTask.payload["dedup_key"].astext == ...`, real Postgres JSONB query).
If you ever want a "has this exact thing already been decided" check from
your own code (e.g. before re-raising something from a handler), this is the
function to call rather than a bespoke query.

Current `dedup_key` conventions, in case any of these tasks show up in your
queue during testing and the key looks unfamiliar:

- `collision:{min(id_a, id_b)}:{max(id_a, id_b)}` — `merge_characters`
- `cross_book:{candidate_id}:{target_id}` — `merge_across_books`
- `chapter:{chapter_id}` — `confirm_chapter_split`
- `reclassify:{book_id}:{surface_form}` — `classify_candidate`, raised when
  discovery proposes a surface form again after a human already verified its
  rejection (`RejectedCandidate.human_verified`)

## be1 → orchestrator · SCR-1 needs a decision, not urgently

`plans/sprint-7/SCR.md` SCR-1 asks for a seventh payload shape
(`confirm_field`) to close the one remaining `human_verified` disagreement
case that doesn't fit any of the six frozen types: a verified `Character`'s
own `aliases`/`importance_tier` disagreeing with a same-book rerun. The guard
itself (never overwrite) is complete and tested without it — this only
affects whether that specific disagreement reaches the review queue or just
a log line. **Not blocking** anything in this sprint; worth a look before the
next contract freeze if S7.2's resolution handlers end up needing the same
shape for another case.

## be1 → fe1 · nothing new to render this sprint

No new frontend surface from be1's stories — `confirm_chapter_split` and
`classify_candidate` tasks written by this story's code use the exact payload
shapes already frozen in `api/contracts/api.py`, so whatever renderer you
build against those two types from the contract (not from any be1 code)
already covers them.

## Audited, not touched: `api/relations/repository.py`

The story text asks to audit every write path touching `relation`/
`relation_evidence` too. Read, not edited (`api/relations/**` is be2's) —
guards already exist there (`.where(Relation.human_verified.is_(False))` and
the human_verified split at `aggregate_relations`'s active/superseded/kept
lists). Nothing found that needed an SCR.

## Verification

Targeted: `api/tests/extraction`, `api/tests/pipeline`, `api/tests/reconcile`,
`api/tests/workers` — 353 passed. New/changed coverage: `TestReplaceCandidates
PreservesVerifiedRejections`, `TestQueueCollisionReview` (`test_repository.py`,
extraction), `TestQueueCrossBookReview` (new `test_repository.py`, reconcile),
the extended `TestUpsertChapters` chapter-disagreement cases and
`test_a_verified_characters_fields_reject_a_disagreeing_rerun` (pipeline/
extraction `test_repository.py`), and `test_verification.py` (new, pipeline)
for `raise_disagreement`/`record_correction_feedback` directly. One
pre-existing test's assertion (`test_service.py::TestDeathBlocksAutolink`)
updated to match the now-correct `merge_across_books` payload shape — the
scenario it tests (death blocks an autolink) is unchanged, only the payload
shape it reads back changed.

`ruff check`/`ruff format --check` clean on every changed file.

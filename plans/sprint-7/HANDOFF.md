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

# Sprint 7 — Handoff

## devops-1 — S7.11, S7.12

### S7.11 — Review-queue metrics and alerting

`api/ops/review_metrics.py` behind two new routes:

- `GET /ops/review-metrics` — queue depth by task type, open-task age
  (p50/p90/max hours), median time-to-resolve, accepted/corrected/rejected
  outcome mix, and correction rate grouped by pipeline stage.
- `GET /ops/review-alerts` — queue-depth threshold breach, tasks open >48h,
  and orphaned graph threads (a thread paused on an interrupt with no open
  review task pointing at it).

`ReviewResolution.decision` (`api/contracts/api.py`) is a freeform string with
no fixed vocabulary — S7.4 hadn't landed a resolve handler as of this writing,
so there is nothing to bucket it against yet. The accepted/corrected split is
derived instead from `CorrectionFeedback.model_value != human_value`, which is
stable regardless of what `decision` strings S7.4 ends up using. Once S7.4
lands and a real vocabulary exists, it would be worth cross-checking that the
`decision` string and the `model_value`/`human_value` diff agree — they
should, but nothing currently asserts it.

Orphaned-thread detection reads `checkpoint_writes` directly for LangGraph's
reserved `__interrupt__`/`__resume__` channels rather than compiling a graph —
see the comment on `_PAUSED_THREADS_SQL` in `review_metrics.py`. It groups by
`thread_id` only, not `(thread_id, checkpoint_ns)`; fine while nothing uses
subgraphs, worth revisiting if S7.1's ingestion graph introduces nested ones.

Two new routes bumped `api/tests/pipeline/test_books_routes.py`'s frozen path
count 43→45 (SCR-2, `plans/sprint-7/SCR.md`) — be1-owned file, do1 filed
rather than fixed it directly.

### S7.12 — Chaos testing (`scripts/chaos_test.py`, `make chaos-test`,
`.github/workflows/nightly-chaos.yml`)

Six scenarios. Same `INTEGRATION_HOST` gate as `perf_smoke.py` (S6.15):
report-only everywhere except the integration host or the nightly workflow's
own disposable GitHub Actions stack, per BRANCH.md §9. Also refuses to run
under `INTEGRATION_HOST=1` if `ingestionstage` shows a `RUNNING` row updated
in the last 10 minutes — treated as another agent's live pipeline, not a
stale row.

**Verified for real** against the shared dev stack (`INTEGRATION_HOST=1`,
containers actually killed and restarted):

- Kill `celery-worker` mid-review (via `api/tests/graph/checkpoint_probe.py`,
  Sprint 1's baseline interrupt/resume graph — S7.1's real ingestion graph
  hadn't merged as of this writing; swap the thread once it does) → **PASS**,
  state and resume value survived a real `docker compose kill`.
- Kill `db` mid-resolve → **PASS**, the pre-kill checkpoint was still on
  Postgres's volume and resumed correctly after restart.
- Kill `api` mid SSE-stream → **PASS**, a fresh query after restart answers
  normally.
- Two reviewers resolving the same task concurrently / resolving a task whose
  thread already completed → **SKIP**, `POST /api/review/tasks/{id}/resolve`
  (S7.4, be2) is still the frozen 501 stub. The script inserts a throwaway
  `reviewtask` row directly (same "not my dependency" convention as
  `test_integration_ingestion.py`'s straight-to-Postgres project creation) and
  cleans it up in a `finally`; starts asserting for real the moment S7.4 lands.
- **Network partition between the worker/api and Neo4j → FAIL, and this is a
  real finding, not a script bug**: disconnecting the `neo4j` container from
  the compose network and calling `api.graph.client.execute` from the `api`
  container hangs past a 20-second bound instead of raising a clean, fast
  error. `api/graph/client.py`'s driver has no connection/query timeout
  configured for this path. **Runbook candidate for be2**: a real network
  partition to Neo4j in production would hang whatever request triggered the
  call (a query, an upsert) rather than failing fast and letting a caller
  retry or surface an error — worth a bounded timeout on
  `driver.verify_connectivity()`/`session.run()` in `get_driver()`/`execute()`.

Two bugs found and fixed in the harness itself while verifying, worth knowing
about if you extend it:

- `docker network connect` with no `--alias` reconnects a container but drops
  its compose-assigned service-name DNS alias — every other container
  resolving it by service name (`neo4j`, not the container name) breaks
  silently afterward. The reconnect in scenario 6's `finally` now passes
  `--alias neo4j` explicitly. (Found the hard way: an earlier manual test run
  left the shared dev stack's `api`/`celery-worker` containers unable to
  resolve `neo4j` at all until reconnected with the alias restored.)
- `main()` originally collected all scenario results in one list
  comprehension — one scenario raising an uncaught exception lost every other
  scenario's already-computed result. Each scenario now runs in its own
  try/except inside the loop.
- Scenarios 1/2 need the checkpointer's `checkpoints`/`checkpoint_writes`
  tables to exist; `ensure_checkpointer_schema()` runs
  `setup_checkpointer()` once under `INTEGRATION_HOST=1` before the scenario
  loop (idempotent, same call `test_checkpointer.py`'s session fixture makes).

Not built: an SCR was not needed for S7.12 — everything it needs already
exists (Sprint 1's checkpointer, the `/health` endpoint, `/api/query`). No
hook was requested from be2; scenarios 4/5 simply skip until S7.4 lands.

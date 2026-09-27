# Sprint 5 — Schema Change Requests

Checked `plans/sprint-5/SCR.md` in the sibling worktrees (be1, be2, do1) before
numbering: none had filed one. fe1 starts at SCR-1 / DCR-1.

### SCR-1 · fe1 · 2026-09-26

**Need:** `CharacterOut` (the project roster list contract,
`GET /projects/{id}/characters`) carries `appears_in_books: list[int]`
(presence only) but no per-book mention count. `CharacterDetailOut` already
has the real data via `appearances: list[AppearanceOut]`.

**Why:** S5.10's appearance strip is specified to weight each book slot "by
mention count," but the roster is hundreds of characters — an N+1 detail
fetch per row to get real weights is the same trade-off Sprint 3's SCR-1
already rejected for the per-chapter sparkline. Every filled slot on the
roster row currently renders at uniform intensity (`AppearanceStrip`'s
`intensity` prop degrades gracefully to `1` when absent) rather than
fabricating a distribution. The character detail page's own strip *does* use
real per-book intensity, since `CharacterDetailOut.appearances` already has
it.

**Blocking:** no — the strip's presence/absence and its always-visible text
caption ("books 1–3") already answer the acceptance question ("which books is
this person in"); only the *relative weight* between filled slots is
degraded.

**Proposed:** add `appearances: list[AppearanceOut]` to `CharacterOut`
directly (same shape `CharacterDetailOut` already declares), or a lighter
`mentions_by_book: dict[int, int]` keyed by `series_order`. Either removes
the degraded-intensity note in `web-app.md` and `character-row.tsx`.

### SCR-2 · fe1 · 2026-09-26

**Need:** `CharacterDetailOut.mentions_per_chapter` is one histogram keyed by
chapter *number*, but a multi-book character's chapter numbers reset every
book — book 1's chapter 3 and book 2's chapter 3 collide under the same key
`"3"`.

**Why:** the character detail page's mentions timeline used to trust this
field directly (Sprint 3). For a series character it would silently merge
two different chapters' counts into one bar.

**Blocking:** no — worked around client-side. `character-detail.tsx` now
derives its own per-book histogram from the paginated mention list (which
does carry `book_id`) plus that book's own chapter ranges
(`chapterKeyForPage`), and offers a book selector so the timeline is always
scoped to one volume rather than trusting the aggregate field.

**Proposed:** nest the field per book (`mentions_per_chapter:
dict[str, dict[str, int]]` keyed by `book_id`, or drop it from
`CharacterDetailOut` in favour of `AppearanceOut` carrying its own
per-chapter histogram) at the next freeze.

---

### DCR-1 · fe1 · 2026-09-26

**Need:** the design canvas (`design/canvas/*.dc.html`) and `design/DESIGN.md`
§4 have no artboard or component spec for `project-overview`, `series-roster`,
or `series-arc` — §1's table names them for this sprint, but they were never
authored (the canvas is still `Ask / CharacterDetail / CharacterList /
EvidencePanel / GraphExplorer / Library / Main / UploadProgress`, unchanged
since Sprint 4).

**Why:** S5.9–S5.12 build four new or substantially-extended screens with no
canvas rationale or frozen component spec to build from, unlike every prior
sprint's screens.

**Blocking:** no — built directly from `design/DESIGN.md` §2's settled
direction (parchment grounds, typographic `<PageRef>`, dot-and-word status,
stroke-pattern relation families) and §3's tokens, extrapolating the existing
component vocabulary rather than inventing a new one:

- `<AppearanceStrip>` (`routes/project/appearance-strip.tsx`) reuses the same
  "never colour alone" rule as the relation-family legend — every band has a
  visible text caption, not just an `aria-label`.
- The book-filtered graph and the series-position control extend
  `<GraphCanvas>`/`<RelationArc>`'s existing "layout once, animate the
  filter" and "one code path for one state or many" rules rather than adding
  new ones.
- Project screens (`project-list.tsx`, `project-new.tsx`,
  `project-overview.tsx`) reuse `<PageHeader>`/`<EmptyState>`/card patterns
  from the Sprint 1 library screen verbatim.

**Proposed:** author the three artboards in the canvas and back-fill
`design/DESIGN.md` §4 with `<AppearanceStrip>` and the series graph/arc specs
at the next freeze, so a future sprint has the versioned spec this one had to
extrapolate.

### SCR-3 · fe1 · 2026-09-26

**Need:** `api/contracts/series.py` (named in the onboarding brief as the
frozen home of `ReconcileCandidate`/`ReconcileDecision`/`SeriesPosition`/
`AppearanceOut`/`RelationArcOut`) does not exist. Those five symbols are
real and frozen, but split across `api/contracts/extraction.py`
(`ReconcileCandidate`, `ReconcileDecision`), `api/contracts/pipeline.py`
(`SeriesPosition`), and `api/contracts/api.py` (`AppearanceOut`,
`RelationArcOut`).

**Why:** a future agent briefed the same way would grep for a file that
was never created and lose time before finding the symbols split across
three existing files.

**Blocking:** no — verified directly against the actual files before
building against them, per the same brief's own instruction to check the
contracts directly.

**Proposed:** either add a thin `api/contracts/series.py` that re-exports
these five names for a single import surface, or correct the sprint brief
text to name the real files.

---

### SCR-4 · do1 · 2026-09-26
**Need:** `api/tests/pipeline/test_books_routes.py`'s frozen route-count
assertion (`assert len(response.json()["paths"]) == 38`) needs bumping to 40.
**Why:** S5.14 added two do1-owned routes to `api/routes/ops.py`
(`GET /ops/reconciliation-quality`, `GET /ops/reconciliation-order-check`),
same class of change as SCR-3 in `plans/sprint-3/SCR.md`. do1 does not own
`api/tests/pipeline/**` (be1) and cannot edit it directly.
**Blocking:** no — same as SCR-3's precedent, this is a known, understood
test-count drift, not a real regression. Land whenever be1 next touches that
file, or batch it into the merge train.
**Proposed:** bump the literal `38` to `40` in that one assertion.

### SCR-5 · do1 · 2026-09-26
**Need:** `pipeline.reconcile_characters` (`api/pipeline/tasks.py`, be1-owned,
S5.1/S5.2) needs a per-project Postgres advisory lock
(`pg_advisory_xact_lock(hashtext(project_id::text))` or equivalent) held for
the duration of the reconcile stage.
**Why:** S5.15's acceptance criterion is "eight books ingest unattended with
no duplicate characters from races" — two books in the same project
reconciling concurrently race against the same project roster and can each
independently decide a candidate is new, creating a duplicate `Character`
row neither run alone would produce. do1 owns the orchestration
(`scripts/ingest_series.py`) and the concurrency **eval** (`eval/
identity_metrics.py`'s duplicate-rate scoring, wired to
`GET /ops/reconciliation-quality`) but cannot add the lock itself:
`api/pipeline/**` and `api/workers/**` are be1-owned, and the lock has to be
acquired inside the Celery task, not from an external script. Until it
lands, `scripts/ingest_series.py --concurrent` is a **stress-test harness
only** — it can and is expected to surface duplicates, not a proof they
cannot happen.
**Blocking:** yes for S5.15's own DoD line ("per-project reconcile lock
proven under concurrent load"), not for S5.13/S5.14, which do not depend on
it.
**Proposed:** be1 adds the advisory lock at the top of
`_reconcile_characters` in `api/pipeline/tasks.py` (or inside `api/
reconcile/`'s own entry point), released automatically at transaction end.
No schema change, no migration -- an SCR because it is a cross-agent
dependency, not because it touches a frozen file.

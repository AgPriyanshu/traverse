# Sprint 4 — Schema Change Requests

### SCR-13 · be2 · 2026-09-23

**Need:** nullable `asserted_by_character_id` (FK `character`, on delete set null) on `relation_evidence`, and `evidence_ids: list[UUID]` on `RelationOut`.

**Why:** F3.4 attributes each dialogue quote to a speaker and S4.7 path hops must carry evidence ids. Today the speaker is stored only per edge (`relation.asserted_by_character_id`, the most frequent speaker of a hearsay edge), so `EvidenceOut.asserted_by` repeats the edge speaker on every dialogue item. Hop evidence ids are reachable only via `GET /relations/{id}/evidence`.

**Blocking:** no.

### SCR-14 · be2 · 2026-09-23

**Need:** `first_chapter`/`last_chapter` on `GraphEdgeOut` (same as fe1's SCR-11, be2 will populate from the Neo4j edge properties once it lands), and `EvidenceOut.span` (SCR-10) is out of reach: evidence rows carry no span.

**Blocking:** no.

### SCR-15 · be2 · 2026-09-23

**Need:** Sprint 4 plan says migration `0009` adds `relation`/`relation_evidence`. They exist since `0006` (head is `0007`), so no relation migration is needed. Only be1's SCR-1 tables are outstanding. Please correct the plan text.

**Blocking:** no.

---

Checked `plans/sprint-4/SCR.md` in the sibling worktrees before numbering: none had filed one. be1 starts at SCR-1.

---

### SCR-1 · be1 · 2026-09-23

**Need:** models and the Sprint 4 migration for `scene`, `scene_participant` and `dialogue_line`. `plans/sprint-4/README.md` says migration `0009` holds only `relation`/`relation_evidence`, and `api/db/models/**` has no scene or dialogue model. Those relation tables already exist since `0006`, so `0009` is not needed for them. The three S4.8/S4.9 tables exist nowhere.

**Why:** S4.8 and S4.9 persist into them, and be2's pass-2 batching reads them. be1 cannot write models or migrations.

**Blocking:** yes for persistence and for be2's scene batching. All of be1's logic (segmentation, cascade, prefilter) is built and unit-tested without them. The repository (`api/pipeline/scene_repository.py`) uses SQL text against the names below, so it works unchanged once they land.

**Proposed** (the exact names and columns the repository queries):

```
scene(
  id uuid pk,
  book_id uuid fk book on delete cascade,
  chapter_id uuid null fk chapter on delete set null,
  position int not null,                 -- document order within the book
  page_start int not null, page_end int not null,
  chunk_ids uuid[] not null,
  created_at, updated_at
)
index (book_id, position)

scene_participant(
  scene_id uuid fk scene on delete cascade,
  character_id uuid fk character on delete cascade,
  mention_count int not null,
  primary key (scene_id, character_id)
)
index (character_id, scene_id)           -- the co-presence self-join

dialogue_line(
  id uuid pk default gen_random_uuid(),
  book_id uuid fk book on delete cascade,
  chunk_id uuid fk documentchunk on delete cascade,
  char_start int not null, char_end int not null,
  speaker_character_id uuid null fk character on delete set null,
  method text not null,                  -- explicit_tag | narration | alternation | llm | unresolved
  confidence float not null,
  created_at, updated_at
)
index (book_id), index (chunk_id), index (speaker_character_id)
```

Explicit `__tablename__` values `scene`, `scene_participant`, `dialogue_line` (SQLModel's default would give `sceneparticipant` and `dialogueline`). `book_id` and `position` are additions to the plan's column lists: `book_id` on `dialogue_line` for delete-by-book, `position` for document order.

Add all three to `api/tests/conftest.py::TABLES_TOUCHED_BY_TESTS` (`dialogue_line`, `scene_participant`, `scene`, before `documentchunk`).

---

Numbered after checking the sibling worktrees: be1 filed SCR-1 and fe1 filed
SCR-9 to SCR-12, so do1 starts at SCR-13. Renumber at the merge train if
another agent landed one in between.

---

### SCR-16 · do1 · 2026-09-23

**Need:** bump the frozen OpenAPI path count in
`api/tests/pipeline/test_books_routes.py::TestStillFrozen` (be1-owned) by 2.
do1 added `GET /ops/relation-quality` and `GET /ops/relation-cost`
(`api/routes/ops.py`). Same collision as Sprint 3 SCR-3; a subset check would
end the recurring bump.

**Blocking:** the count assertion fails on this branch until bumped.

---

### SCR-17 · do1 · 2026-09-23

**Need:** pass-2 per-run cache and prefilter counters on `IngestionStage` (or
`StageRecord`): `prefix_cached_tokens`, `chunks_seen`, `chunks_skipped`.
`GET /ops/relation-cost` currently derives chunks processed from
`relations.extract`'s `rows_written` (be2 must write the number of chunks sent
to the model there) and reads the prefix-cache hit rate from vLLM's cumulative
counters, which blend every run since the server booted.

**Why:** a per-book cache hit rate is only exact if the stage records its own
window. Interim: the nightly job differences counters where it can
(`api/ops/vllm_metrics.hit_rate_between`).

**Blocking:** no.

---

fe1 numbers from SCR-10 and DCR-5 (DCR-1 to DCR-4 were Sprint 3) so a common-ancestor collision with be1's SCR-1 or be2's next number cannot happen again (see `plans/sprint-2/RETRO.md`).

---

### SCR-10 · fe1 · 2026-09-23

**Need:** an optional `span: SpanBox | None` on `EvidenceOut`, the same shape `SpanBox` already has for page-viewer highlights.

**Why:** S4.12 acceptance is "every evidence item reaches its page in one click with the right span highlighted". `EvidenceOut` has `quote`, `page_start` and `page_end` but no coordinates, and `PageRenderOut.spans` cannot be tied to a quote client-side. Today the evidence item links to the page (`<PageRef>`) with no highlight.

**Blocking:** no. One click reaches the page; only the highlight is missing. Same gap as Sprint 3 SCR-9 (`MentionOut.span`), and the same fix, probably in the same stage.

**Proposed:** `span: SpanBox | None = None` on `EvidenceOut`, populated where `relation_evidence` is written. fe1 will append `?highlight=x,y,w,h` to the `<PageRef>` link as soon as it exists (the page route already parses that parameter).

### SCR-11 · fe1 · 2026-09-23

**Need:** first and last chapter on `GraphEdgeOut` (`first_chapter: int | None`, `last_chapter: int | None`), matching `RelationOut`.

**Why:** the graph filters by chapter range and the relationship rows show a chapter span. `GraphEdgeOut` carries only `page_refs`, so fe1 derives chapters by joining each ref's page against `/books/{id}/chapters`. That works but is approximate (only the cited pages, not the relation's true validity range) and is exactly the hook Sprint 8's spoiler slider needs to be exact.

**Blocking:** no.

**Proposed:** add both fields, additive and defaulted to `None`.

### SCR-12 · fe1 · 2026-09-23

**Need:** `GET /api/projects/{id}/graph` documented as book-scoped by `book_id`, and confirmation that a single-book project's `book_id` filter returns character nodes only for that book.

**Why:** the screen is `/books/:id/graph`. fe1 calls it with `project_id` from `BookOut` and `book_id` set. If `book_id` is ignored the book screen silently shows the whole series.

**Blocking:** no, assuming the filter works as its name says.

---

### DCR-5 · fe1 · 2026-09-23

**Need:** a `relation.structural` colour token (light and dark), plus a line-style entry for it in `design/DESIGN.md` §3.

**Why:** the ontology and `RelationFamily` have five families; §3 defines four colours and four line styles. fe1 draws `structural` in the muted ink (`fg.muted`, 5.6:1 light and 7.0:1 dark) with a long-dash pattern `16 3` so it is still distinguishable by line style. That is a placeholder, not a design.

**Blocking:** no.

**Proposed:** one token, validated at 4.5:1 on paper, surface and sunken in both themes. `tests/contrast.test.ts` already checks the four existing relation colours, so the new one only needs adding to its list.

### SCR-18 · be2 · 2026-09-25

**Need:** be1 to check `"Mr. Darcy"` / `"Mr. Fitzwilliam Darcy"` and
`"Mrs. Collins"` / `"Charlotte Lucas"` on the live Pride and Prejudice
project — these look like the same two people each split across two
`Character` rows rather than merged by the alias cascade (`plans/sprint-4/HANDOFF.md`
has the full finding). Not a schema change; filing here because it was found
running be2's pass 2 against be1-owned data, not something be2 can fix from
`api/relations/**`.

**Blocking:** no, but it is a real recall loss — any relation naming
"Fitzwilliam Darcy" resolves ambiguously between the two rows and is dropped
as off-roster.

**be1 reply · 2026-09-25:** Both symptoms are already fixed by the
`sprint-4-roster3` rules on `ai-master` (given-name dominance for a bare
surname, and a generational/kinship guard tightened to only qualify a shared
given name). The live P&P roster you saw was stale — `RESOLVE_ALIASES` for
that book last ran 2026-09-24, before roster3 merged; nothing had re-run it
since. Re-ran it live just now (worker already carried the current code): the
roster now merges Darcy/Fitzwilliam/FITZWILLIAM DARCY/Mr. Fitzwilliam Darcy
into one 374-mention character, and Lady Lucas is no longer an alias of
Charlotte Lucas. `Mrs. Collins`/`Charlotte Lucas` stay two rows — her mention
contexts never announce or co-reference the marriage, so there is no textual
cue to merge on; recorded as a real limitation in `HANDOFF.md`, not forced.
Pass 2 needs a re-run against this now-current roster for the recall number to
reflect it — that re-run is yours to trigger.

---

### SCR-12 · fe1 reply · 2026-09-26

**Not resolved.** Verified live on the shared stack (project
`6146f7d0-…`, book `4d5750ce-…`): `book_id` does not scope the node list at
all. `api/graph/queries.py::_NODES` matches `(c:Character {project_id: $pid})`
with no `book_id` predicate whatsoever; only `_EDGES` filters by
`$book IN r.book_refs`. Confirmed by calling the route with a `book_id` from a
*different project* (Wuthering Heights' book id against the P&P project) —
the response still returns all 72 P&P nodes (only edges go to zero, because
no edge's `book_refs` contains that foreign book id). Every current project
is single-book, so this is invisible today (project's characters == that
book's characters), but it will surface the moment Sprint 5 lands a
multi-book series project: a reader on book 1 of a series would see every
character from every later book in the node list, just with no edges drawn
to them. `api/graph/**` is be2-owned; fe1 cannot fix this. Recommend treating
as blocking for Sprint 5, not this sprint's ship gate.

### SCR-19 · fe1 · 2026-09-26

**Need:** the original source PDF re-uploaded (or the render cache
backfilled) for both ingested books in object storage, or `render_page`
(`api/pipeline/render.py`) to fail with a clearer, non-500 error when it's
absent.

**Why:** verifying S4.12's "click a page reference → real page viewer" against
the live stack, every page request 500s:
```
api.pipeline.storage.StorageError: GET books/4d5750ce-5a9b-42c4-a8c0-70b24a69c6e8/source.pdf
failed: 404 NoSuchKey
```
`mc ls` on the shared MinIO bucket confirms it: `books/4d5750ce-…/` holds only
`relations_extracted.json`; there is no `source.pdf` and no cached
`pages/*.png`. Same for Wuthering Heights (`books/6e165994-…/` doesn't even
exist as a prefix). Parsing, chunking, character extraction and pass 2 all
completed successfully for both books, so the PDF was available *during*
ingestion — it just never landed (or no longer exists) at the object-storage
key `render_page` reads from on demand. This is not a frontend bug: the
citation link builds the right URL, lands on the right page number
(confirmed against a real evidence page ref), and — once the Chakra/TanStack
retry budget (2 retries, exponential backoff) exhausts after ~4-5s — shows a
correct, graceful "Something went wrong / HTTP 500 / Try again". But the page
image itself cannot render for either book right now, which blocks the
literal, visual half of the ship-gate promise ("every edge click-through to
the pages that prove it"). `api/routes/books.py` / `api/pipeline/render.py`
are be1-owned; the MinIO bucket lifecycle is do1-owned. fe1 cannot fix this
from `web/src/**`.

**Blocking:** for the visual page-image acceptance criterion, yes. Citation
routing, page numbering and error handling are all independently verified
correct.

**Proposed:** re-upload `source.pdf` for both books at
`books/{book_id}/source.pdf` in the shared MinIO bucket, or point
`render_page`'s `storage_key` at wherever the original upload actually still
lives if it's just a key mismatch.

### Finding (not schema, ops) · fe1 · 2026-09-26

**Transient Neo4j/Postgres desync after `resolve_aliases` reruns.** Before
touching anything, per this session's instructions, checked
`ingestionstage` for `state='RUNNING'` on the shared `postgres` DB and found
`EXTRACT_RELATIONS` (run `eac52ada-…`) stuck `RUNNING` since
2026-09-25T11:25, attempt 6, no `finished_at` — `celery inspect active`
showed nothing running and the worker container had been recreated since, so
per this session's instructions (stale vs. genuine judgment call) it was left
alone rather than touched. Root cause, worked out from the data rather than
guessed: be1's live `resolve_aliases()` call (2026-09-25T11:13–11:20,
see the SCR-18 follow-up above) recreated every `Character` row with new
UUIDs; `relation.subject_character_id`/`object_character_id` cascade-delete
on `character`, so the *previous* `AGGREGATE_RELATIONS`/`UPSERT_GRAPH` run's
28 Postgres `relation` rows were wiped, while Neo4j — upserted before the
alias fix — still held all 28 edges and 72 nodes under the old, now-deleted
character ids. `GET /relations/{id}/evidence` 404'd for every single edge in
the live graph as a result (verified in a real browser: the evidence drawer
opened, header and confidence rendered from the stale Neo4j edge, but the
citation list correctly showed a graceful "Not found" with retry — no
crash). A fresh `relations.extract` run (attempt 7) started mid-session
(2026-09-26T05:22, not triggered by fe1) and completed by 05:33, restoring
consistency (29 fresh edges, ids matching current `relation` rows) — this
finding is informational, not a live blocker, by the time you read it. Flagging
because the failure mode is structural: nothing currently reconciles Neo4j
against a `resolve_aliases` rerun automatically, so any future roster fix
will orphan the graph the same way until `graph.upsert` is re-triggered by
hand. Worth a retro item (be1/be2/do1): either `resolve_aliases` should kick
the relations chain itself, or the nightly (S4.15) should alert on a
Neo4j edge whose `graph_edge_id` no longer resolves in Postgres, the same way
it already alerts on evidence-free edges.

### SCR-19 · do1 reply · 2026-09-26

**Root cause found — not `render_page`, not a key mismatch, not a lifecycle
expiry.** The two demo books' `source.pdf` objects were deleted, not missing.
`docker-compose.yml`'s `test` compose service never overrode `MINIO_BUCKET`,
so it inherited `${MINIO_BUCKET:-traverse-int}` from `&api-env` — the same
bucket `api`/`celery-worker` write to — unlike Postgres, which already has a
dedicated `traverse_test` database for exactly this reason.
`api/tests/pipeline/test_books_routes.py`'s `client()` fixture teardown calls
`await store.delete_prefix("books/")` after **every** test. Every
`docker compose --profile test run --rm test` this sprint (mine included) was
therefore deleting `books/*` from the live bucket — the demo books' source
PDFs and any rendered page cache — not just from an isolated test slice. This
also explains the Wuthering Heights book's prefix not existing at all:
`delete_prefix("books/")` has no book scoping, so one test run anywhere wipes
every book's objects, not just the one the test created.

**Fixed** the same way `traverse_test` isolates Postgres: `traverse-test` is
now its own MinIO bucket (`MINIO_BUCKETS` in `.env.example`,
`docker-compose.yml`'s `minio-init` default, `docker/minio/init-buckets.sh`'s
own fallback, and `scripts/bootstrap_databases.sh`'s bucket list — four copies,
not three, since that script builds its list independently rather than
reading the shared default). The `test` service now sets
`MINIO_BUCKET: ${TEST_MINIO_BUCKET:-traverse-test}`, mirroring
`TEST_POSTGRES_DB`. Verified concretely, not just by config inspection:
uploaded a fresh book through the live API (`POST
/api/projects/{id}/books`, book `cbf36af0-…`), confirmed `source.pdf` in
`traverse-int`, ran the full suite (`423 passed, 1 skipped`) twice, confirmed
`source.pdf` (plus the pipeline's own `chapters.json`) still present in
`traverse-int` after both runs, and confirmed `traverse-test` stayed empty
(tests clean up their own bucket now, harmlessly). Checked Neo4j for the same
class of bug per this session's brief: **not affected** — Community edition's
single-database limitation means it was never isolable the way Postgres/MinIO
are, but `api/tests/graph/conftest.py`'s `clean_project` fixture scopes every
test to a fresh random `project_id` and `reset_project()` only deletes that
one project's nodes, so sharing the live database has always been safe by
construction. No fix needed there; noted in `infra-topology.md` so nobody
re-investigates it.

**Not fixing:** the two demo books' PDFs are already gone from `traverse-int`
— that's this sprint's SCR-19 symptom, and the isolation fix only stops
recurrence going forward. Re-uploading them is be1/orchestrator's call (whoever
owns the demo corpus), not a do1 action from here.

Files: `docker-compose.yml`, `.env.example`, `docker/minio/init-buckets.sh`,
`scripts/bootstrap_databases.sh`. Memory map updated: `infra-topology.md`.

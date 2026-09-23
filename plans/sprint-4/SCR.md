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

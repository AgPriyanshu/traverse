
## be2 → all · pass 2, aggregation, projection and read APIs (S4.1 – S4.7)

- **Stages.** `relations.extract` stages validated facts as `books/{id}/relations_extracted.json` in object storage (nothing is an edge yet). `relations.aggregate` recomputes the **whole project** from raw evidence (this book's facts plus other books' evidence rows), so book order never matters, and replaces every non-`human_verified` relation. `graph.upsert` projects the project into Neo4j in one write transaction.
- **be1 inputs.** `api/relations/inputs.py` imports `api.pipeline.prefilter.pass2_candidates(book_id, session=...)` and falls back to a local distinct-character rule when absent. `api/relations/speakers.py` imports `api.pipeline.scene_repository.list_dialogue_lines` and falls back to the model's `asserted_by`. Both are lazy imports: neither exists on `ai-master` yet, so the real-signature path is **untested** until be1 merges (A-3.3). Re-check on merge.
- **Deviation from be1's note.** An unresolved dialogue speaker keeps the fact `dialogue` (edge becomes hearsay, no speaker) rather than `narrated`; marking it narrated would state a character's claim as fact.
- **Predicate to family map** is `api/graph/ontology.yaml` (`GET /graph/ontology`). I added transitions from acquaintance/friend/rival/enemy to engaged/married so the Elizabeth–Darcy arc is legal.
- **Stored direction.** Postgres holds one canonical direction per fact (`parent_of` over `child_of`, symmetric pairs sorted by character id). Neo4j also holds materialised inverse edges (`inverse: true`); reads for the explorer use `inverse: false` only.
- **GraphOut** is unchanged. `page_refs` are `PageRefOut{book_order, page}`; the Postgres fallback used to return bare ints and is fixed. `truncated` is set at 2000 edges. `limit_*` filters on the edge's and node's first position; page refs are not trimmed, so a later cited page can be visible on an early edge (spoiler caveat for S8).
- **Evidence pagination.** `GET /relations/{id}/evidence?limit=&offset=`, ordered by (book, chapter, page, id), 404 for an unknown relation. `GET /relations/arc?a=&b=` returns all states for the pair in either direction, one element if nothing changed. `GET /graph/path?from=&to=` takes character ids, `max_hops` capped at 4; no path returns `found=false`.
- **Rejection stats** (off-roster rate etc.) are logged and stored in the artifact's `summary`. Reasons: unknown_predicate, not_extractable, off_roster_subject/object, self_relation, empty_quote, quote_not_in_chunk, quote_names_other_characters.
- **Confidence formula** is in `api/relations/aggregate.py` (0.5 count, 0.3 agreement, 0.2 mean item confidence).
- Filed SCR-13 to SCR-15.

---

# Sprint 4 — Handoff

## be1 → be2 · scene, participant, dialogue and prefilter query shapes (S4.8 – S4.10)

**Blocked on SCR-1** (`plans/sprint-4/SCR.md`): the `scene`, `scene_participant`
and `dialogue_line` tables and models do not exist on `ai-master`, and be1 may
not write either. All code below is built against the table shapes SCR-1
proposes and reads them through SQL text, so it works unchanged once they land.
Until then `build_scenes_and_speakers` logs a warning and skips (it checks
`to_regclass`), so `resolve_aliases` still succeeds.

Everything lives in `api/pipeline/`; import from there.

```python
# scene_repository.py
async def list_scenes(session, book_id) -> list[SceneRow]
#   SceneRow(id, chapter_id, page_start, page_end, chunk_ids: list[UUID],
#            participants: dict[UUID, int])          # character_id -> mention_count
#   document order. Batch pass 2 by these.

async def characters_sharing_scene(session, character_id, *, book_id=None)
#   -> list[tuple[UUID, int]]   (other character, shared scene count), most first

async def list_dialogue_lines(session, book_id, *, chunk_id=None) -> list[DialogueLineRow]
#   DialogueLineRow(chunk_id, char_start, char_end, speaker_character_id | None,
#                   method, confidence)
#   offsets are into DocumentChunk.text and include the quote marks.

# prefilter.py
async def pass2_candidates(book_id, *, min_roster_mentions=2, session=None) -> list[ChunkRef]
#   ChunkRef(chunk_id, scene_id | None, chapter_id, page_start, page_end, roster_mentions)
#   document order. Group by scene_id to batch by scene.

async def prefilter_stats(book_id, *, min_roster_mentions=2, session=None) -> PrefilterStats
#   PrefilterStats(total_chunks, candidates, reduction_ratio)
```

Semantics you need:

- **`speaker_character_id = NULL` means unresolved.** `method` is then
  `"unresolved"` and `confidence` 0. Mark those edges `narrated`, do not guess.
  Resolved methods: `explicit_tag` (0.95), `narration` (0.65), `alternation`
  (0.5 – 0.62, decays with run length, capped at 6 in a row), `llm` (at most
  0.8, only above 0.5 and only for someone in the scene's roster).
- A quoted span with fewer than two alphanumeric characters is not a line.
- `pass2_candidates` counts **distinct** roster characters per chunk, not raw
  mentions: one person named three times cannot form a relation. A chunk with
  exactly one distinct character is kept when its scene has two or more
  participants. Mentions come from `character_mention` (chunk level, resolved).
  A chunk with no scene row falls back to the mention rule alone.
- Scenes are produced at the tail of `pipeline.resolve_aliases`, not a stage of
  their own: `api/tasks.py` is frozen and has no scene stage. They are rebuilt
  wholesale on every run of that stage.
- `character_mention` has no `char_start`/`char_end` populated (pass 1 stores
  the chunk's first page). Speaker attribution therefore re-locates names by
  scanning chunk text with each character's aliases and surface forms; a form
  shared by two characters in the same chunk is ignored rather than guessed.

## be1 → orchestrator · S3.4 co-presence

The plan says S3.4's co-presence check "approximates same scene with same
chunk". `api/extraction/collision.py` has **no co-presence check at all** (only
first-token qualifier, generational, kinship and lifespan), so there is nothing
to back-fill and the two-Catherines test is untouched. Scene-level co-presence
also cannot run inside alias resolution: scenes need resolved characters, which
alias resolution is still producing. A naive "two forms in one scene means two
people" rule would split real characters, since "Elizabeth" and "Miss Bennet"
share scenes constantly. If wanted, the safe version is a post-hoc check on
pairs that already share a first token; scoping it is a decision for the retro.

`tier_by_participation` still uses distinct chunks as a stand-in for scene
breadth. It can switch to `scene_participant` counts once SCR-1 lands, but it
runs before scenes exist, so that needs a re-tier after the scene stage.

## Not measured yet

- Scene size on the seeded corpus (acceptance 3 – 8 chunks), co-presence query
  latency (< 50 ms), speaker accuracy on a hand-labelled chapter, unresolved
  rate, prefilter reduction ratio and recall cost. All need scene tables and
  a real ingest; see `STANDUP.md` for what was run.


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

---

## do1 -> be2, be1, orchestrator

### S4.14 relation quality

- `make eval-relations BOOK=pride-and-prejudice` prints the table
  (per-predicate P/R/F1, spurious rate, direction accuracy, temporal arcs,
  citation accuracy, evidence-free counts, pass-2 cost). Backed by
  `GET /ops/relation-quality?book_id=` and `GET /ops/relation-cost?book_id=`.
- Gold: `eval/gold/pride_and_prejudice/relations.yaml`, 33 relations over the
  12 protagonist/major characters, pinned to the corpus checksum, closed world
  over in-scope pairs (`ignored_predicates` are exempt). Four temporal arcs
  (Elizabeth/Darcy, Jane/Bingley, Collins/Lucas, Wickham/Lydia). Chapter labels
  were read from the public text and are approximate; scoring tolerance is 3
  chapters. Relationships outside the ontology (aunt, cousin, patron) are not
  labelled. **Wuthering Heights is not labelled yet.**
- Matching is after inverse normalisation, so be2 may emit `child_of` or
  `parent_of`; a reversed pair is a direction error and a strict miss.
- Citation accuracy: `make judge-citations BOOK=pride-and-prejudice` (50
  seeded samples, resumable), writes `citation_judgements.json`. It needs
  `GET /relations/{id}/evidence` (S4.7) and the graph route live. **Not yet
  judged; the 95% number does not exist yet.**
- Evidence-free edges are checked in Postgres and Neo4j; the PR workflow and
  nightly fail if either is non-zero.

### S4.15 cost and rebuild

- be2: the drill calls the Celery task `graph.upsert` with `(book_id,)` and
  expects it to be idempotent, standalone (no ingestion run required) and to
  clear `stale`. Wall clock includes the task. `relations.extract` must set
  `rows_written` to chunks sent to the model (see SCR-17).
- `make graph-rebuild BOOK=<key>`, `make graph-rebuild-drill` (synthetic graph,
  wired into `make test-integration`). The drill refuses to pass on an empty
  graph.
- The nightly posts pass-2 cost, appends `pass2-cost-trend.jsonl` and fails on
  a cache hit rate under 80%.
- **Fixed a latent bug:** `api/ops/vllm_metrics.py` read only the pre-V1
  `vllm:gpu_prefix_cache_*` names; be2's S3.9 spike saw the unprefixed ones, so
  the hit rate was probably always `None`. Both are read now.

### Carried items

- `test` image tag: `TEST_IMAGE_TAG` (compose default falls back to
  `TRAVERSE_TAG`), set by make to the worktree directory name and by `make env`
  into `.env`. For bare compose: `TEST_IMAGE_TAG=$(basename $PWD)`.
- vLLM cache path: mounted at `/models` with `HF_HOME=/models/huggingface`.
  Not verified on a GPU cold start.
- `make ingest BOOK=<key>` (`scripts/ingest_book.py`): reuses a ready book,
  otherwise uploads and polls.
- Docker credentials: make now sets `DOCKER_CONFIG` to `.docker-nocreds/`
  (`{}`) when `docker-credential-desktop.exe` fails; `NOCREDS=0/1` overrides.
  See infra-topology.md.

### Incident to know about

Running `docker compose --profile test run` from this worktree recreated the
shared `db` and `rabbitmq` containers (compose config drift against the running
stack); they came back healthy within about a minute with volumes intact.
Anyone mid-run around that time may have seen a dropped connection.

---

# Sprint 4 — Handoff

## fe1 → be2

- The graph screen calls `GET /api/projects/{project_id}/graph?book_id=...` with the book's `project_id`. It renders `nodes`, `edges`, and `truncated`, filters client-side, and needs `page_refs` on every edge (the chapter filter and span derive from them, SCR-11).
- Edge click calls `GET /api/relations/{id}/evidence?limit=10&offset=n` and expects chapter-ordered results with the sort key stable across pages. The client re-sorts within a page only.
- The evidence panel calls `GET /api/relations/arc?a=<source>&b=<target>` using the edge's `source` and `target`. States need `first_chapter`, `last_chapter` (null = open ended) and `page_refs[0]` as the transition citation; a state with no page ref renders "no page cited".
- Character detail uses `GET /api/characters/{id}/neighbourhood?depth=1` and reads only its edges touching the character.
- `GraphEdgeOut.evidence_count` sets the edge width and the panel's "of N" total.

## fe1 → orchestrator

- `web/src/lib/api/schema.d.ts` was regenerated from `app.openapi()` (the committed file predated the Sprint 4 freeze). Docstrings now appear as comments, which is generator behaviour.
- New deps: `cytoscape`, `cytoscape-fcose` (no types, so `web/src/types/cytoscape-fcose.d.ts`).
- Filed SCR-10, SCR-11, SCR-12 and DCR-5 in `plans/sprint-4/SCR.md`.

## do1 -> be1: complete gold rosters and tier-scoped roster metric

- `eval/gold/pride_and_prejudice/roster.yaml` now lists 52 characters (every
  named person on the story pages, one-line ones as `mentioned`); Wuthering
  Heights 23 (animals and Biblical names excluded). Same corpus checksum pins.
- `GET /ops/extraction-quality` adds `roster_named_*` (protagonist+major+minor).
  Same matching; an unmatched prediction counts only if it claims a named tier,
  a prediction matched to a `mentioned` gold character is dropped. Overall
  numbers are unchanged in definition. Definition is in
  `eval.metrics.roster_precision_recall_f1_for_tiers`.
- Known gaps: the Harringtons, the Webbs, old Mr. Darcy and Wickham's father are
  not labelled (plural or alias collision).

## be2 → all · real run on Pride and Prejudice, post-verifier (2026-09-25)

Ran `relations.extract` → `aggregate` → `upsert` on the live stack (book
`4d5750ce-…`, 72-character roster, thinking disabled, output capped at 6144
tokens). Two runs: before and after adding `api/relations/verify.py` (a
second LLM pass that grades each accepted quote against its claim alone,
fails closed).

**Numbers**

| | before verifier | after verifier |
|---|---|---|
| pass-2 wall clock | 675s (11.2 min) | 731s (12.2 min) |
| chunks read (of 719, be1 prefilter) | 231 | 231 |
| calls / length-limit splits | 257 / 13 | 257 / 13 |
| validator-accepted facts | 156 | 90 |
| verifier-rejected | n/a | 46 |
| facts persisted | 156 | 44 |
| edges after aggregation | 74 | 28 |
| evidence-free edges (Postgres + Neo4j) | 0 / 0 | 0 / 0 |
| prefix-cache hit rate (`/metrics` delta) | 0.69 | 0.68 |
| `GET /ops/relation-quality` precision / recall / F1 | 0.577 / 0.455 / 0.508 | 0.818 / 0.273 / 0.409 |

Pass 2 completes well inside the 25-minute ingestion budget (12.2 min).
**Zero evidence-free edges confirmed by direct query on both stores** —
`MATCH ()-[r:RELATED]->() WHERE r.evidence_count=0 RETURN count(r)` → 0,
`SELECT count(*) FROM relation r WHERE NOT EXISTS (SELECT 1 FROM
relation_evidence e WHERE e.relation_id=r.id)` → 0. The upsert guard has never
been exercised by a real zero-evidence edge in this run, but it is the same
code path S4.6's unit test forces.

**Prefix-cache hit rate misses the 80% target** (~68–76% across three runs
today, all measured on the shared integration host, not a worktree). Not
investigated further — plausibly the concurrent-chunk fan-out (16-wide)
interleaves requests from other purposes' calls on the same vLLM instance in
a way that evicts the block cache before a same-book request returns to it;
worth a dedicated look before the writeup leans on a number.

**Cost.** `GET /ops/extraction-cost` does not yet have `relations.extract`,
`relations.aggregate` or `graph.upsert` line items (only pipeline stages
appear) — do1-owned, filing as a finding rather than fixing directly. Raw
vLLM counters for the after-verifier run: 524,237 prompt tokens, 252,409
generation tokens for the whole pass (extraction + verification calls
together, not separated).

**Rejection breakdown, after-verifier run** (`accepted`+`rejected` totals the
attempted extractions, before the verifier's second pass):
```
endpoint_not_in_chunk: 495   predicate_cue_missing: 476
quote_names_neither_endpoint: 334   quote_not_in_chunk: 283
quote_names_other_characters: 118   off_roster_object: 46
self_relation: 17   off_roster_subject: 5
off_roster_rate: 2.7%
```
`predicate_cue_missing` and `endpoint_not_in_chunk` are new checks added this
run (see S4.2 fix below) and account for most of the reduction from the
earlier 156-fact run.

**Bug found and fixed before this run (`c0917f8`):** the roster block sent to
the model included pass-1 descriptors ("Mr. Darcy - landowner; brother to
Miss Bingley"). The model copied descriptor text back as a "quote" and
treated its own paraphrase ("brother to Miss Bingley") as narrative evidence
— 493 of the run's 1,753 candidates were this. Fixed by stripping descriptors
from the prompt roster (names and aliases only) and adding two new
validator checks: the cited quote must actually name both endpoints in the
full chunk text (`endpoint_not_in_chunk`), and it must contain a cue word for
the specific predicate claimed (`api/relations/cues.py`,
`predicate_cue_missing`) — `married_to` needs "wife/husband/married", not
just two names in the same sentence.

**Verifier trade-off, honestly:** it raised precision from 0.577 to 0.818
(still short of the 0.90 target) but cut recall from 0.455 to 0.273 (badly
short of the 0.80 target) — it is not calibrated, and being the same local
Qwen3-8B model rather than a frontier judge, it is a self-consistency filter,
not an independent check, and it still let a wrong edge through (below). The
Elizabeth/Darcy arc that had three states (antagonistic → engaged → married)
in the pre-verifier run is two states now (acquaintance → married,
chapter 44 → 58, cited) — a real relation was cut along with the noise.
**Recall is the more useful axis to invest in before Sprint 8's calibration
work**, not further precision tightening.

**Hand-checked sample — all 28 aggregated edges** (fewer than the ~40 asked
for; the whole graph only has 28 after the verifier). Verdict is mine, reading
the full chunk, not just the cited quote:

| subject → predicate → object | page | verdict |
|---|---|---|
| Jane sibling_of Elizabeth Bennet | 219 | correct |
| Mr. Bennet parent_of Miss Lydia Bennet | 195 | correct |
| Lady Catherine de Bourgh employer_of Mr. Collins | 50 | correct (patron of his living) |
| Elizabeth Bennet friend_of Charlotte Lucas | 21 | correct |
| Mr. Darcy acquaintance_of George Wickham | 58 | correct |
| Mrs. Bennet parent_of Miss Lydia Bennet | 144 | correct |
| Mr. Bennet parent_of Jane | 243 | correct |
| Elizabeth Bennet sibling_of Miss Lydia Bennet | 198 | correct |
| Colonel Fitzwilliam guardian_of Darcy | 123 | correct — "Darcy" here is Georgiana (alias "Miss Darcy"), not the protagonist |
| Elizabeth Bennet married_to Mr. Darcy | 241 | correct |
| Elizabeth Bennet acquaintance_of Mr. Darcy (superseded) | 165 | correct |
| Elizabeth Bennet friend_of Mrs. Gardiner | 160 | **weak** — quote is Darcy asking to meet "her friends" (the Gardiners), doesn't itself establish Elizabeth/Mrs. Gardiner as friends (they're aunt/niece) |
| Mr. Bennet parent_of Mary | 243 | correct |
| Mr. Bennet parent_of Elizabeth Bennet | 243 | correct |
| Jane friend_of Mr. Bingley | 24 | **wrong predicate** — passage describes Bingley's romantic attention to Jane, not friendship |
| Miss de Bourgh engaged_to Mr. Darcy | 224 | **wrong** — this is Lady Catherine's disputed claim in dialogue (mislabeled `narrated`), and Darcy denies it later in the book |
| Mr. Denny colleague_of George Wickham | 57 | correct |
| Mrs. Gardiner parent_of Elizabeth Bennet | 154 | **wrong** — Mrs. Gardiner is Elizabeth's aunt; quote only mentions the Gardiners' own children |
| Mrs. Collins married_to Mr. Collins | 119 | correct fact, but "Mrs. Collins" and "Charlotte Lucas" are two separate `Character` rows for one person — a be1 alias-resolution gap, not a relation bug |
| Caroline Bingley sibling_of Mr. Bingley | 35 | correct |
| Mrs. Gardiner acquaintance_of Mr. Darcy | 98 | **wrong** — the quote says "the **late** Mr. Darcy" (the protagonist's deceased father); resolved to the living Mr. Darcy, a name-collision the roster has no separate entry for |
| Mr. Bingley friend_of Mr. Darcy | 20 | correct |
| Mr. Gardiner acquaintance_of Mr. Darcy | 165 | correct |
| Darcy sibling_of Mr. Darcy | 241 | correct (Georgiana / Fitzwilliam) |
| Mr. Collins married_to Charlotte Lucas | 88 | correct |
| Elizabeth Bennet acquaintance_of George Wickham | 62 | correct |
| Mr. Gardiner parent_of Mrs. Gardiner | 154 | **wrong** — spouses, not parent/child; quote only names their (unlisted) children |
| Mrs. Gardiner parent_of Mr. Gardiner | 154 | **wrong**, same bug reversed |

21 clearly correct, 3 imprecise/disputed, 4 clearly wrong (fabricated or
misattributed) → **hand-checked precision ≈ 75%** counting imprecise as
wrong, **≈ 86%** counting only the clear fabrications — either way **short
of the 90% target**, roughly matching the gold-set number (81.8%).

**A specific gap the verifier did not catch:** both Gardiner-Gardiner edges
come from one quote, "Mr. and Mrs. Gardiner, with their four children," which
correctly names both endpoints (satisfying `endpoint_not_in_chunk`) and
contains the cue word "children" (satisfying `predicate_cue_missing`) without
the predicate holding *between the two named people at all*. The verifier
(same local model, `purpose=adjudicate` has no frontier route today) missed
it too. **The cue and endpoint checks are necessary but not sufficient**:
neither confirms the predicate holds specifically between subject and
object, only that suitable words are present somewhere in the quote. A
proper fix needs either a frontier judge for `adjudicate`, or a check that
the cue word sits nearer one candidate pairing than the alternative — not
attempted here; flagging for Sprint 8's calibration pass.

**Roster fragmentation found, be1-owned:** `Character` has both `"Mr. Darcy"`
and `"Mr. Fitzwilliam Darcy"` as separate rows for the same person (plus
`"Darcy"` = Georgiana, correctly separate). Any fact naming "Fitzwilliam
Darcy" resolves ambiguously between the two Darcy rows and is dropped as
off-roster rather than attributed — a real recall loss, and distinct from
the collision-review path (S3.4), which never flagged these as the same
person. Also `"Mrs. Collins"` / `"Charlotte Lucas"` did not merge. Filed as
SCR-18 below rather than touched directly (`api/extraction/**` is be1's).

**Temporal arc:** `GET /relations/arc?a=<Elizabeth>&b=<Darcy>` returns two
states — `acquaintance_of` (ch. 44, superseded) → `married_to` (ch. 58,
active), each with its citation page. Works as designed, though thinner than
the pre-verifier three-state arc (see trade-off above).

**Graph density / PRD §12.2:** 28 edges over 72 characters = 2,016 possible
directed pairs (72×71/2 unordered), density ≈ **1.1%**. This is sparse enough
that most character pairs who plainly share the book's scenes (per be1's
`scene_participant`) have **no** explicit edge at all. **Recommendation:
build `co_occurs_with` from scene co-presence** (already modelled in
`ontology.yaml` as `extracted: false`, so no schema change needed) — at this
density an explorer graph would look nearly empty otherwise, and it is a
cheap, non-LLM signal that does not compete with the precision problem
above. Not implemented this run (no time left in the pass); a small addition
to `graph.upsert` reading `scene_participant` directly.

## be1 → be2, orchestrator · SCR-18 follow-up — stale roster, not a new bug

The Darcy/Lucas splits SCR-18 reported were already fixed by
`sprint-4-roster3` (`api/extraction/aliases.py`'s `_dominant`/`_surname_rule_vetoes`,
`api/extraction/collision.py`'s tightened generational/kinship checks). The
live P&P `character` table was stale: `RESOLVE_ALIASES` last ran
2026-09-24T01:12, before roster3 merged to `ai-master`; nothing re-ran it
since, including the celery-worker rebuild that picked up be2's SCR-18 pass-2
work. Verified the worker's `/app/api/extraction/{aliases,generations}.py`
byte-identical to this checkout before touching anything, confirmed no stage
was `RUNNING`, then called `pipeline.resolve_aliases('4d5750ce-...')`
directly (bypassing the Celery chain, so pass 2/graph upsert did not
re-trigger) — 73 characters written, Darcy and Lucas both correct. Regression
tests: `api/tests/extraction/test_darcy_lucas_merges.py`, built from the real
candidate rows, model stages stubbed to always say "same person" so only the
deterministic rules are under test.

**Still two rows, and will stay two rows:** `Charlotte Lucas` / `Mrs. Collins`.
Her stored mention contexts (capped per candidate, same cap as every
candidate) never co-reference the two names — no "Mrs. Collins, formerly Miss
Lucas" or equivalent. A maiden/married-name merge here would be guessed from
convention alone, which is exactly the failure mode `collision.py`'s whole
design exists to avoid. If this needs closing, the real fix is a textual
cue (marriage-announcement detection feeding the pass-1 sweep, or a wider
context window per candidate), not a rule that assumes every "Mrs. X" married
a "Miss Y" from the same book.

**For be2:** pass 2 for P&P (`EXTRACT_RELATIONS`/`AGGREGATE_RELATIONS`/
`UPSERT_GRAPH`, last run 2026-09-25T10:46–10:58) ran against the *stale*
roster, before this fix landed live. The 0.273 recall number is measured
against that stale roster; worth a re-run against the current one before
trusting the number as roster3's ceiling rather than a mix of two bugs.

---

## fe1 → all · S4.11–S4.13 verified against the real stack (2026-09-26)

Branch `ai/fe1/sprint-4-verify`. Everything below was checked in a real
headless browser (Playwright, installed locally for this session — not
committed, no project dependency added) against the live API on
`localhost:8000`/`:5174`, project `6146f7d0-…`, book `4d5750ce-…`.

**No `web/src/**` code changes were needed.** Every real-data path I could
drive — graph canvas, list view, evidence drawer, character-detail
relationships, `RelationArc`, 400px, dark mode, keyboard-only interaction —
rendered correctly or degraded gracefully (a real `ErrorState` with retry,
never a blank crash or an infinite spinner). Full pass: `pnpm lint`,
`pnpm tsc --noEmit`, `pnpm build` all clean; `docker compose --profile test
build test-web` + `run --rm test-web` → 166/166 passing, unchanged.

**Real graph is much smaller than 900 edges.** 73 characters / 29
relationships live right now (be2's aggregation is intentionally
conservative post-verifier — see be2's numbers above). List view and graph
view both read correctly at this scale; nothing about the small size broke
anything.

**900-edge target checked with a synthetic 60-node/900-edge payload**
(`page.route` intercepting the graph fetch, not committed anywhere — a
throwaway script). Loaded in ~1.8s, a family-filter toggle updated the
canvas in well under 300ms, no console errors, `hideEdgesOnViewport`/
`textureOnViewport`/layout-computed-once all behaved as designed. I'm
confident the current approach plausibly holds at 900; I did not benchmark
on this shared host per BRANCH.md §9 (shared vLLM/GPU note doesn't apply
here, but the box is still shared, so treat the ms numbers as directional).

**400px and dark mode**, both against real P&P data: no horizontal overflow
at 400px (list view auto-selects below 47em, per the existing
`matchMedia` default), dark-mode canvas colours and legend all legible.
Screenshots aren't committed; happy to regenerate on request.

**SCR-12 (book_id scoping): confirmed NOT resolved.** See the SCR.md reply
above — `_NODES` in `api/graph/queries.py` never filters by book, only
`_EDGES` does. Invisible today (every project is single-book); will leak in
Sprint 5. be2-owned, not fixed here.

**Evidence panel and citations: verified against real quotes.** Once a
live, in-progress pass-2 re-run (not started by fe1 — see the SCR.md finding
below) finished mid-session, evidence items showed real cited text ("Of Mr.
Darcy it was now a matter of anxiety to think well...", p. 165-168, ch. 44,
narrated) and a correct single-state `RelationArc`. The current live corpus
has **no pair with more than one relation state** (every arc is flat), so
the 2-state and 3-state paths could not be re-confirmed against real data
this session — they're still covered by the existing unit suite (166 green)
and were exercised visually last sprint per the prior standup entry.

**Page-ref click-through: routing and error handling verified; images
cannot render.** Clicking a citation lands on the exact right page number
(matches the evidence item's `page_start`). But `GET
/api/books/{id}/pages/{n}` 500s for every page of both ingested books — the
source PDF was never persisted (or no longer exists) at
`books/{book_id}/source.pdf` in the shared MinIO bucket, confirmed by `mc
ls`. Filed as SCR-19. The frontend's own behaviour here is correct: a
loading skeleton, then (once the query client's 2-retry backoff exhausts,
~4-5s) a real "Something went wrong / HTTP 500 / Try again" — no blank
placeholder, no crash. SCR-10's evidence `span` field also still hasn't
landed, so there's nothing to highlight yet even once an image renders.

**A live data-integrity issue self-resolved mid-session** — see the SCR.md
finding for the full timeline (Neo4j left orphaned relative to Postgres
after a `resolve_aliases` rerun regenerated character ids, cascade-deleting
`relation` rows; a fresh pass-2 run someone else kicked off fixed it while I
was mid-verification). Recommending a retro item so it can't silently
recur unnoticed next time; not something to fix from `web/src/**`.

## be2 → all · re-run after the semaphore fix and be1's live roster correction (2026-09-26)

**Bug found and fixed:** re-triggering `relations.extract` a second time in the
same worker process crashed in 1.8s with `Semaphore ... bound to a different
event loop`. `api/llm/client.py::semaphore()` kept a single process-wide
`asyncio.Semaphore`; each Celery task wraps its body in its own
`asyncio.run(...)` (a fresh loop per task, same worker process), and
`Semaphore.acquire` binds to whichever loop first awaited it. Fixed by
rebuilding the semaphore whenever the running loop differs from the one it
was created on (`api/llm/client.py`, regression test in
`api/tests/llm/test_client.py`). This is a previously-latent bug, not
introduced this sprint — any worker child handling two LLM-calling tasks in a
row would have hit it eventually, for any purpose.

**Re-ran pass 2** on the same book after be1's live roster fix (Fitzwilliam
Darcy merged, 73-character roster) and the semaphore fix:

| | before (broken roster) | after (roster + semaphore fix) |
|---|---|---|
| completion | 731s (12.2 min) | 651s (10.8 min), no crash |
| edges after aggregation | 28 | 29 |
| evidence-free edges (Postgres + Neo4j) | 0 / 0 | 0 / 0 |
| prefix-cache hit rate | 0.68 | 0.67 |
| `GET /ops/relation-quality` P / R / F1 | 0.818 / 0.273 / 0.409 | **1.0 / 0.333 / 0.5** |

The roster fix helped recall (0.273 → 0.333) but **not enough** — still less
than half the 0.80 target. Precision on the gold overlap is 1.0, but the gold
set only covers a subset of predicates; my own hand-check of all 29 edges
found 2 clearly wrong (**~93% hand-checked precision** — see below), close to
target but the gold number is optimistic.

**Hand-check of the 29 edges, this run:** 27 correct, 2 wrong.
- **Wrong:** `Mrs. Gardiner sibling_of Mr. Gardiner` — they are spouses. The
  quote, "Mr. Gardiner was a sensible, gentlemanlike man, greatly superior to
  his sister," is about Mr. Gardiner's actual sister **Mrs. Bennet**, not his
  wife; the model (or roster resolution) attached "his sister" to the wrong
  person entirely.
- **Wrong:** `Sir William Lucas parent_of Miss Lydia Bennet` — the quote
  ("Sir William Lucas himself appeared, sent by his daughter to announce her
  engagement") is about Sir William's real daughter (Charlotte/Miss Lucas);
  the object resolved to Lydia Bennet instead, who is not named in the
  chunk's engagement passage at all.
- Both are the same class of gap named in the earlier run: the endpoint and
  cue checks confirm words are *present somewhere in the chunk*, not that the
  predicate holds *between exactly this pair*. Still unresolved — a
  proper fix needs the verifier (or the extractor) to reason over the
  antecedent of pronouns like "his sister" / "her daughter", which a
  substring-based check cannot do.
- **Duplicate fact, not wrong:** `Elizabeth Bennet sibling_of Miss Bennet` is
  the same fact as `Elizabeth Bennet sibling_of Jane` — `"Jane"` and
  `"Miss Bennet"` are still two separate `Character` rows for Jane Bennet.
  Same class of roster fragmentation as SCR-18, not fixed by be1's Darcy/Lucas
  correction; still costing real recall (a fact naming "Miss Bennet" and one
  naming "Jane" split into two edges instead of merging into one with more
  evidence).

**Honest bottom line: the roster fix was real and helped, but it is not the
whole story.** Recall (0.333, best case) is still under half the 0.80 DoD
target after both fixes. The remaining gap is pass-2 extraction coverage
itself (231 of 719 chunks read; the extractor still declines to extract many
real relationships the prose states) and the cited-quote-vs-claim precision
class of bug above, not roster quality. **Sprint 4's relation-quality DoD is
not met** — precision is plausibly close (93-100% depending on measurement),
recall is not (0.33 vs 0.80).

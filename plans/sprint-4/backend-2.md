# Sprint 4 · Backend Engineer 2 — **ship gate owner**

**Branch:** `ai/be2/sprint-4-graph` · **Worktree:** `../traverse-wt/be2`

## Mission

Pass 2 of the PRD's central architectural bet (§5.2), and the graph it produces.
You own the ship gate. If something has to be cut this sprint, cut breadth of
predicates, never evidence anchoring or temporal validity — those two are what
make the product different from a chatbot.

## Owned paths

`api/relations/**`, `api/graph/**`, `api/query/**`, `api/llm/**`,
`api/routes/{graph,characters,query}.py`

---

## S4.1 — `relations.extract` (pass 2)

Roster-informed extraction, per chunk, with the roster in the **prompt prefix**
so vLLM's prefix cache serves it once per batch instead of per chunk.

Prompt structure — prefix stability is the whole cost argument, so the roster and
ontology block must be **byte-identical across every call for a book**:

```
[STABLE PREFIX]  ontology.prompt_fragment()
                 roster: canonical name | aliases | one-line descriptor
                 extraction rules + few-shot examples
[VARIABLE]       chapter N · pages X–Y
                 <chunk text>
```

Sort the roster deterministically. A dict iteration order change breaks the
cache silently and doubles your cost with no error.

If S3.9 found a 60-character roster does not fit: tier-filtered roster
(protagonist + major always; minor only when mentioned in this chunk's chapter),
falling back to per-chapter rosters. Record which strategy was used per book —
it is an ablation row in Sprint 8.

Emit `ExtractedRelation` with subject, predicate, object, assertion type,
speaker, **quote (≤400 chars, ETH-3)**, chunk id, confidence.

*Acceptance:* Prefix-cache hit rate ≥ 80% during a full pass-2 run, visible in
do1's dashboard. Full novel pass 2 completes within the PRD's ≤25 min total
ingestion budget, or the retro says what it cost and what to do about it.

## S4.2 — Off-roster validator

S3.9 asked whether the model invents characters. Assume yes.

Reject, before persistence, any relation whose subject or object does not match
a `Character.canonical_name` or a known alias — using **exactly the
normalisation be1 documented in Sprint 3's HANDOFF**. A mismatch here silently
drops real edges, which is the worst kind of bug: invisible recall loss.

Rejections are counted and logged by reason, never silently dropped. A high
off-roster rate means the prompt is wrong, and you can only see that if you
count it.

Also reject: self-relations, predicates outside the ontology, quotes that do not
appear in the cited chunk (a cheap substring check that catches fabricated
evidence outright).

*Acceptance:* Off-roster rate reported per book. The quote-substring check
catches an injected fabricated quote in a test.

## S4.3 — `relations.aggregate` (F3.5)

40 chunks asserting the same relation become **one edge with 40 evidence
items**, not 40 edges.

Group by `(subject, predicate, object)` after inverse normalisation — an edge
extracted as `child_of` in one chunk and `parent_of` (reversed) in another is
the same fact and must merge. Materialise the inverse on upsert (S4.6), and
canonicalise symmetric predicates by sorting the pair so `sibling_of(A,B)` and
`sibling_of(B,A)` never both exist.

Edge confidence from evidence count, agreement, and per-item confidence — **not
a model self-report** (the PRD is explicit about this). Publish the formula in
code with a comment explaining each term; Sprint 8 calibrates it and needs to
know what it is calibrating.

Genuine contradictions that are **not** temporal transitions (two different
stated fathers) → a `resolve_conflict` review task row. Do not resolve by
confidence tiebreak; the PRD forbids it and the honest answer is "a human
decides".

*Acceptance:* A synthetic book with 40 assertions of one relation produces one
edge with 40 evidence items. Inverse and symmetric duplicates collapse correctly.

## S4.4 — Temporal validity (F3.3)

Order evidence by chapter. When a later relation legally supersedes an earlier
one (`ontology.is_legal_transition`), **close the earlier edge** by setting
`last_chapter` and `status='superseded'`, and open a new edge. Never overwrite —
the history is the interesting part.

`GET /relations/arc?a=&b=` returns the ordered sequence with the citation at
each transition. This is what the demo's step 5 renders.

*Acceptance:* Elizabeth↔Darcy shows an arc with a cited transition, not a flat
`married_to`. A pair with no transition still returns a single-element arc —
fe1 renders one code path.

## S4.5 — Assertion provenance (F3.4)

Classify each evidence item `narrated` / `dialogue` / `inferred`, with
`asserted_by` for dialogue — using be1's S4.9 speaker attribution rather than
asking the model twice.

An edge whose evidence is *only* dialogue is marked `hearsay=True`. Sprint 6's
answers must attribute those ("According to Mrs Bennet...") rather than stating
them as fact. In fiction, a character asserting a relationship is a plot device,
not a truth claim.

*Acceptance:* A *Frankenstein* edge established only inside Walton's letters is
marked `hearsay`, with the speaker recorded.

## S4.6 — `graph.upsert` (F3.2)

Project Postgres into Neo4j. **Reject at upsert any edge with zero evidence
items** — the PRD's hard rule, implemented as a guard that raises, not a filter
that skips.

Denormalise onto the edge: `page_refs` (sorted unique pages), `evidence_count`,
`predicate`, `family`, `first_chapter`, `last_chapter`, `status`,
`assertion_type`, `hearsay`. Traversals then answer "which pages" without a
Postgres round trip; full quotes hydrate on click.

Materialise inverse edges so traversal never depends on extraction direction.

Batch with `UNWIND` — one Cypher per edge on a 900-edge graph is minutes of
round trips.

*Acceptance:* `MATCH ()-[r:RELATED]->() WHERE r.evidence_count = 0 RETURN count(r)`
returns 0, always. `make graph-rebuild` produces a byte-identical projection.

## S4.7 — Graph read APIs

```
GET /projects/{id}/graph       ?book_id=&families=&min_confidence=&limit_book_order=&limit_chapter=
GET /characters/{id}/neighbourhood   ?depth=1|2
GET /relations/{id}/evidence   full quotes + pages, paginated
GET /graph/path?from=&to=&max_hops=4
```

`chapter_lte` filters on `first_chapter` — Sprint 8's spoiler mode, wired now.
Cap `max_hops` at 4; an uncapped shortest-path on a dense graph is a denial of
service you inflict on yourself.

*Acceptance:* Full graph for a 60-character novel returns in <300ms.
Path query returns every hop with its evidence IDs.

---

## DoD

- [ ] Relation P ≥ 90%, R ≥ 80% on major pairs, measured by do1's harness
- [ ] Zero evidence-free edges, proven by query
- [ ] Temporal arcs demonstrated on three known relationships
- [ ] Prefix-cache hit rate ≥ 80% and pass-2 cost per novel recorded
- [ ] Graph fully rebuildable from Postgres
- [ ] `HANDOFF.md`: `GraphOut` shape, predicate→family map, evidence pagination

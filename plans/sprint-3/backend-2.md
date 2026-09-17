# Sprint 3 · Backend Engineer 2

**Branch:** `ai/be2/sprint-3-characters` · **Worktree:** `../traverse-wt/be2`

## Mission

Serve the roster, provide the similarity service be1's alias cascade depends on,
and **de-risk Sprint 4 by prototyping relation extraction a week early**. Sprint
4 is the ship gate; discovering on its Tuesday that Qwen3-8B cannot hold a
50-character roster in a prompt would cost the gate. Find that out this week.

## Owned paths

`api/graph/**`, `api/relations/**`, `api/query/**`, `api/retrieval/**`,
`api/llm/**`, `api/routes/{characters,graph,query}.py`

---

## S3.6 — Character read APIs

```
GET  /api/projects/{id}/characters   ?tier=&q=&book_id=&sort=mentions|first_page|name
GET  /api/characters/{id}            record + aliases + attributes + evidence
GET  /api/characters/{id}/mentions   ?chapter_lte= , paginated, page-ordered
```

`CharacterDetailOut` carries a per-chapter mention histogram — fe1's timeline
(S3.11) needs it, and computing it client-side from paginated mentions is wrong.
One grouped SQL query, not N+1 over chapters.

`chapter_lte` on every character endpoint from day one. Sprint 8's spoiler mode
(F4.5) must be enforced at the query layer, and adding the parameter to five
endpoints later is how it gets missed on one of them.

*Acceptance:* Roster for a 60-character novel returns in <200ms. Mentions
endpoint paginates over 2,000 rows without loading them all.

## S3.7 — Manual merge and split

```
POST /api/characters/merge   {source_ids: [...], target_id, canonical_name?}
POST /api/characters/{id}/split   {mention_ids: [...], new_canonical_name}
```

Merge must **cascade completely** (F5.4): re-point every mention, union aliases
and attributes, recompute counts/tiers/first-page, delete the source rows, and
mark the survivor `human_verified=True`. Split is the inverse and is what fixes
an over-merged pair of Catherines.

Run in **one transaction**. A half-merged character with orphaned mentions is
worse than no merge, and this endpoint is what Sprint 7's review queue calls, so
it must already be correct when the UI arrives.

*Acceptance:* Merging two characters with 300 combined mentions leaves zero
orphans and a correct union. A merge followed by a split restores the original
partition exactly. Re-running extraction afterwards does not resurrect the
merged-away row.

## S3.8 — Mention-context similarity service

Stage 4 of be1's cascade:

```python
async def cluster_contexts(
    mentions: list[MentionContext], *, threshold: float
) -> list[list[UUID]]
```

Embed contexts with BGE-M3 (reuse the existing model handle — **do not load a
second copy**, BRANCH.md §9), cluster with agglomerative average-link cosine.

Expose the threshold in settings and **report the precision/recall curve across
it** rather than picking 0.82 because it looked reasonable. This threshold
directly controls the false-merge rate, which is the failure mode PRD §11 calls
"catastrophic and silent".

*Acceptance:* Curve committed as a chart or table; be1 sets the threshold from
it. Clustering 2,000 contexts completes in <30s on CPU.

## S3.9 — Sprint 4 de-risk: relation extraction prototype

**Not shipped. A written finding, delivered by Day 4** so Sprint 4 can be
planned against reality.

Build a throwaway script that, for one chapter of *Pride and Prejudice*:

1. Renders the roster into a prompt prefix (`ontology.prompt_fragment()` from
   S1.5 plus canonical names, aliases, one-line descriptors).
2. Runs pass-2-style extraction over that chapter's chunks.
3. Emits `ExtractedRelation` objects.

Answer four questions in `HANDOFF.md`:

1. **How many characters fit?** A 60-character roster plus ontology plus a chunk
   may not fit 16k. If not: tier-filtered rosters, per-chapter rosters, or a
   larger `--max-model-len`? This changes Sprint 4's design.
2. **Does prefix caching actually engage?** PRD §5.2 rests on vLLM reusing the
   roster prefix. Verify with vLLM's cache-hit metrics. If it does not engage,
   the cost argument in the writeup is wrong and Sprint 4 needs a different plan.
3. **Is Qwen3-8B good enough?** Eyeball precision on one chapter. If it is
   poor, Sprint 4 routes `relation_extract` to a frontier API and the ablation
   table reports the split honestly (PRD §11).
4. **Does it invent characters not on the roster?** If yes, the validator must
   reject off-roster subjects and objects — a hard requirement for S4.2.

*Acceptance:* Written findings in `HANDOFF.md` by Day 4, with numbers. A "looks
fine" with no measurements is a failed story.

---

## DoD

- [ ] Character APIs paginated, filterable, `chapter_lte`-aware
- [ ] Merge/split transactional, cascading, tested against orphans
- [ ] Similarity threshold chosen from a measured curve
- [ ] **S3.9 findings delivered Day 4** — this is the sprint's most valuable output
- [ ] `HANDOFF.md`: roster prompt budget, prefix-cache verdict, model verdict

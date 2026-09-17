# Sprint 4 · Backend Engineer 1

**Branch:** `ai/be1/sprint-4-scenes` · **Worktree:** `../traverse-wt/be1`

## Mission

You are be2's supplier this sprint. Pass-2 relation extraction is expensive and
imprecise without three things only the ingestion side can provide: scene
boundaries, speaker attribution, and a prefilter that stops the model reading
chunks with nobody in them. Land all three by **Wednesday** — be2's ship-gate
work is scheduled behind them.

## Owned paths

`api/pipeline/**`, `api/extraction/**`, `api/workers/**`, `api/routes/books.py`

---

## S4.8 — Scene segmentation and co-presence

A *scene* is a contiguous run of chunks sharing a setting and cast. Novels mark
them with blank lines, dinkuses (`* * *`), time jumps, and POV shifts; Docling
preserves enough structure to find most of them.

Persist `scene(id, book_id, chapter_id, page_start, page_end, chunk_ids[])` and
`scene_participant(scene_id, character_id, mention_count)`.

Two things depend on this:

- **be2's pass 2** batches by scene rather than by arbitrary chunk windows, so a
  relation established across a three-chunk exchange is visible in one call.
- **S3.4's co-presence collision check** currently approximates "same scene" with
  "same chunk", which is why it misses some splits. Back-fill it with real
  scenes.

Scene detection does not need to be perfect. A wrong boundary costs a little
recall; no boundaries at all costs be2 the ability to batch coherently.

*Acceptance:* Scenes average 3–8 chunks on the seeded corpus. Co-presence
queries (`which characters share a scene with X`) return in <50ms.

## S4.9 — Speaker attribution

For every dialogue line, who said it. Feeds F3.4's `asserted_by`.

Cascade, cheapest first:

1. Explicit tags — `"..." said Elizabeth`, `Elizabeth replied`
2. Adjacent-narration heuristics — the paragraph before or after names one
   roster member and no other
3. Alternation within a two-party scene — by far the most common case in prose
   and nearly free once scenes exist
4. LLM fallback, batched, **only** for lines the first three cannot resolve

Persist `dialogue_line(chunk_id, char_start, char_end, speaker_character_id,
method, confidence)`. Unresolved is a valid outcome: store `speaker=NULL` rather
than guessing. be2 marks those edges `narrated` instead of falsely attributing a
claim to a character, which is worse than not attributing it at all.

*Acceptance:* ≥80% attribution accuracy on a hand-labelled chapter, with the
per-method breakdown reported. Unresolved rate reported separately — a system
that attributes 100% of lines at 60% accuracy is worse than one that attributes
80% at 95%.

## S4.10 — Pass-2 chunk prefilter

Pass 2 costs an LLM call per chunk. Chunks containing fewer than two roster
mentions cannot yield a character–character relation, and on a typical novel
that is 40–60% of them.

```python
async def pass2_candidates(book_id, *, min_roster_mentions=2) -> list[ChunkRef]
```

Include a chunk with one mention when the **scene** has two or more participants
— a chunk saying "she refused him" carries the relation and names nobody, and
dropping it loses real edges.

Report the reduction ratio. It is an ablation row in Sprint 8 and a headline
number for the writeup: "40% of the corpus never reaches the expensive pass."

*Acceptance:* Reduction measured per novel with recall impact quantified on the
gold set — if the filter costs more than 2 points of relation recall, loosen it
and say so in the retro.

---

## DoD

- [ ] Scenes, speakers, and the prefilter all merged by **Wednesday**
- [ ] S3.4's co-presence check upgraded to real scenes; two-Catherines test still green
- [ ] Speaker accuracy and unresolved rate both reported
- [ ] Prefilter reduction ratio and recall cost measured
- [ ] `HANDOFF.md`: scene/participant/dialogue query signatures for be2 — **Day 2**,
      not Day 5. be2 is blocked on the shapes, not the implementations.

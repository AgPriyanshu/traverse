# Sprint 5 · Backend Engineer 1

**Branch:** `ai/be1/sprint-5-reconciliation` · **Worktree:** `../traverse-wt/be1`
**Owned:** `api/pipeline/**`, `api/extraction/**`, `api/reconcile/**` (new),
`api/routes/books.py`

## Mission

Make book five's Anne the same Anne as book one's. This is Sprint 3's alias
problem one level up, and the failure modes are the same shape but worse: a
false merge across volumes is invisible, permanent, and corrupts every edge on
both characters.

**The governing asymmetry:** a duplicate is visible, recoverable, and mildly
annoying. A false merge is silent, destructive, and users will not catch it.
Bias tight and route the middle band to review.

---

## S5.1 — `pipeline.reconcile_characters` (F2.5)

New stage, after `resolve_aliases`, before `relations.extract`. Add it to the
frozen chain via its task name; do not restructure `api/tasks.py`.

Input: this book's resolved clusters (`book_character_candidate`).
Output: each cluster linked to an existing project `character` or creating a new
one, plus a `character_appearance` row either way.

Cascade, reusing Sprint 3's stages against the **project** roster:

1. exact / normalised canonical match
2. honorific and name-order stripping
3. alias-set overlap — book 3's "Miss Shirley" against book 1's alias list
4. contextual embedding similarity over appearance contexts
5. LLM adjudication on the residue, **with series context in the prompt** —
   "the project already knows Anne Shirley, protagonist of books 1–2, last seen
   as a schoolteacher; book 3 introduces 'Miss Shirley'". Without that framing
   the model is guessing from two name strings.

Record every decision in `reconciliation_decision` with method, confidence, and
`blocked_by`. An unaudited merge is one nobody can review or measure.

*Acceptance:* On *Anne of Green Gables* 1–3, link precision ≥ 95%, recall ≥ 90%.

## S5.2 — Cross-book blocking evidence

Within a book, co-presence in a scene proves two names are different people.
Across books that signal does not exist, so use different evidence:

- **Death.** A character whose death is established in book 2 appearing in book
  5 is a flashback, a namesake, or a resurrection. **Never auto-link.** Populate
  `character_death` from relation/attribute extraction and treat it as a hard
  block that routes to review with the death evidence attached.
- **Contradictory kinship** — the project says X is Y's mother; this book says
  X is Y's daughter.
- **Generational namesakes** — a child named for a parent, which is common in
  family sagas and is Sprint 3's two-Catherines problem across volumes.
- **Tier implausibility** — a protagonist-tier match against a
  mentioned-once candidate is suspicious, not confirmatory.

Blocked matches become `merge_across_books` review tasks (Sprint 7 renders them;
write the rows now).

*Acceptance:* `test_death_blocks_autolink` and `test_generational_namesake`
green. False merge rate ≤ 1% on the series gold set.

## S5.3 — Appearances and recomputation

Write `character_appearance` per character per book: first/last page and
chapter **within that book**, mention count, per-book importance tier, and the
surface forms used in that book. Anne is "Anne Shirley" in book 1 and "Miss
Shirley" in book 3; the appearance holds that, the character holds the union.

Then **recompute the character's derived fields from all appearances** —
`first_book_id`, `first_chapter`, `first_page`, `last_*`, series-wide
`mention_count`, series-wide `importance_tier`. Never accumulate incrementally:
recomputation from the full set is what makes S5.4 possible and is cheap.

Bump `project.roster_version` so the graph projection knows it is stale.

*Acceptance:* Adding a book updates every affected character's derived fields in
one transaction. A character's per-book tiers may differ from its series tier —
a minor character in book 1 who becomes a protagonist in book 4 is correct, not
a bug.

## S5.4 — Order independence

Uploading 3 → 2 → 1 must produce the same graph as 1 → 2 → 3. This falls out of
S5.3 if derived fields are always recomputed and never accumulated — which is
exactly why it is written that way.

Two places that break it if you are careless: reconciliation matching against a
roster that does not yet contain an earlier book's characters (fine — they link
when that book arrives, provided you **re-run reconciliation for the project**
after each book, not just for the new one), and any "first appearance" written
once at creation time.

*Acceptance:* `test_reverse_order_ingestion` ingests a 3-book series both ways
and asserts identical character sets, identical edge sets, and identical derived
fields — by checksum, not by spot check.

---

## DoD

- [ ] Link precision ≥ 95%, recall ≥ 90%, false merges ≤ 1%
- [ ] Every decision audited with its reason
- [ ] Death and namesake blocks tested
- [ ] Reverse-order checksum test green
- [ ] A one-book project still works unchanged
- [ ] `HANDOFF.md` **Day 2**: the project-roster query shape be2's pass 2 needs

# Sprint 3 · Backend Engineer 1

**Branch:** `ai/be1/sprint-3-characters` · **Worktree:** `../traverse-wt/be1`

## Mission

Pass 1 of the PRD's two-pass design (§5.2): find every character, and resolve
the dozen ways a novel refers to each one into a single record. This is the
hardest correctness problem in the project — harder than relation extraction,
because every downstream error traces back to a bad roster.

**Consume from be2 (Sprint 2 handoff):** `api/llm.structured_call`,
`api/llm.budget.plan_batches`. Do not reimplement either.

## Owned paths

`api/pipeline/**`, `api/extraction/**`, `api/workers/**`, `api/tests/extraction/**`

---

## S3.1 — `pipeline.extract_characters` (F2.1)

Sweep every chunk for character-like mentions. **Recall is the objective;
precision is bought back in S3.2 and S3.3.** A character missed in pass 1 does
not exist for the rest of the pipeline.

- Batch with `plan_batches` against the 16k context, reserving output headroom
  proportional to batch size — a 12-chunk batch can emit 60 mentions.
- Per mention emit `CharacterCandidate`: surface form, `chunk_id`, page, chapter,
  **±1 sentence of context**, and a `kind` guess.
- The context field is not optional — it is what S3.3's embedding stage and
  S3.4's collision check both run on. Extracting mentions without context means
  re-reading the book later.
- Extract **all** referring forms: names, honorific forms, epithets ("the old
  woman in the white dress"), role labels ("the housekeeper"). Not pronouns —
  pronoun resolution is pass 2's job with a known roster.
- Dedupe within a batch before persisting; a chunk naming "Elizabeth" nine times
  is one mention row per distinct surface form per chunk, with a count.

*Acceptance:* ≥95% recall of named speaking characters on both labelled novels.
Over-generation is fine and expected — report the raw precision as a baseline so
the retro can show what S3.2/S3.3 recovered.

## S3.2 — Non-character rejection (F2.4)

Places, houses, estates, organisations, ships, deities in oaths, book titles.
"Netherfield" and "Longbourn" are houses; "Providence" is not a character.

Classify with a structured call over the candidate's contexts, and **store every
rejection** with its reason in `rejected_candidate`. Two things depend on this:
the eval harness measures precision loss, and Sprint 7's review queue lets a
human overturn it. A silently dropped candidate is unrecoverable.

Edge case worth handling explicitly: an entity that is both, like a house whose
name is used for its family ("the Bennets of Longbourn"). Keep the person,
reject the place, note the ambiguity.

*Acceptance:* ≥90% roster precision after rejection. No true character is ever
rejected on either labelled novel — a false rejection is far worse than a false
keep, since review can remove but cannot recover.

## S3.3 — Alias clustering cascade (F2.2)

Run in order, cheapest first, each stage only seeing what the previous could not
resolve:

1. **Exact / normalised** — case, punctuation, whitespace.
2. **Honorific and name-order stripping** — `Mr.`, `Mrs.`, `Miss`, `Dr.`, `Lady`,
   `Sir`; Japanese `-san`/`-kun`/`-sama`/`-chan`; `Tokita Kazu` ≡ `Kazu Tokita`.
   Table-driven in `api/extraction/honorifics.yaml`, not inline regexes —
   Sprint 9 adds Russian patronymics for *Anna Karenina* and it must be a data
   change.
3. **Nickname / diminutive tables** — Elizabeth→Lizzy/Eliza/Bess,
   Catherine→Cathy/Kitty, Margaret→Meg/Peggy. Ship a real table; it is high
   precision and free.
4. **Contextual embedding similarity** — cluster mention contexts using be2's
   S3.8 service. Catches epithets no table reaches ("the housekeeper" ≡
   "Mrs Reynolds").
5. **LLM adjudication on the residue only** — a single structured call per
   candidate pair, batched. Expensive; it should see tens of pairs, not
   thousands. If it sees thousands, stages 1–4 are underperforming and that is
   the finding.

Each cluster records **how** it merged (`resolution_method`), so the retro can
report which stage earned its keep.

*Acceptance:* B³ F1 ≥ 0.85. Per-stage contribution reported — if stage 4 adds
less than 3 points it is a candidate for removal, and that belongs in the retro.

## S3.4 — Name-collision splitting

**The sprint's headline test.** Two characters can share a name. String evidence
says "merge"; the truth is "split".

Block a merge when contextual evidence contradicts it:

- **Co-presence** — both surface forms appear in the same scene as distinct
  participants
- **Generational markers** — "young Catherine", "the elder", "her mother's name"
- **Contradictory kinship** — one is described as the other's mother
- **Life-span disjointness** — one first appears after the other's death

On contradiction: keep separate, mark `collision_suspected=True`, and queue a
`merge_characters` review task (Sprint 7 consumes it; write the row now).

Canonical naming must disambiguate: `Catherine Earnshaw` and `Catherine Linton`,
not `Catherine` and `Catherine (2)`.

*Acceptance:* `test_wuthering_heights_two_catherines` passes and is in the
regression suite from now on. `test_no_false_splits` confirms Elizabeth Bennet
does not fragment.

## S3.5 — Character records and tiering (F2.3)

Persist `Character`: canonical name, aliases with per-form counts, first/last
page, first chapter, mention count, attributes with their own evidence spans.

Attributes (occupation, age, family role, physical description) come from a
structured call over that character's top-N mention contexts. **Every attribute
carries a page citation or it is not stored** — the same rule as F3.2, applied
one level up.

**Tiering — measure, do not assume.** Implement both behind
`TIERING_METHOD=mention_count|participation`:

- *mention_count* — percentile thresholds over mention counts
- *participation* — scene count + dialogue-line count + distinct chapters

Score both against a hand-labelled tier list for two novels. The retro records
the winner and PRD §12.5 gets updated.

*Acceptance:* Tier accuracy ≥ 85% for both methods against ground truth, with
the comparison in `RETRO.md`.

---

## DoD

- [ ] Roster P/R/F1 and B³ measured on both labelled novels, in `RETRO.md`
- [ ] Two-Catherines regression test committed and green
- [ ] Per-cascade-stage contribution reported
- [ ] Tiering decided by measurement
- [ ] Extraction stage cost per novel recorded with do1
- [ ] `HANDOFF.md`: `Character.canonical_name` is be2's join key for Sprint 4 —
      document the exact normalisation, because pass-2 relation extraction
      matches on it and a mismatch silently drops edges

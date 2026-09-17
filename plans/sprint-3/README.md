# Sprint 3 — Character Extraction

**Goal:** upload *Pride and Prejudice*, get an accurate character roster —
canonical names, aliases, importance tiers, first-appearance pages — with the
two Catherines in *Wuthering Heights* correctly kept apart.

**PRD refs:** F2.1 – F2.4 · PRD §5.2 pass 1

This is the sprint where quality becomes measurable. Everything before it was
plumbing; from here on, every story has a number attached.

---

## Contract freeze (Day 1)

| Item | Detail |
|---|---|
| Migration `0008` | `character`, `character_mention`, `rejected_candidate` tables; unique `(book_id, canonical_name)`; GIN index on `character.aliases` |
| `contracts/extraction.py` | `CharacterCandidate`, `ResolvedCharacter`, `MergeDecision`, `RejectionReason` finalised |
| `contracts/api.py` | `CharacterOut`, `CharacterDetailOut`, `MentionOut`, `AliasOut` |
| Routes | `GET /books/{id}/characters`, `GET /characters/{id}`, `GET /characters/{id}/mentions`, `PATCH /characters/{id}`, `POST /characters/merge` |

**Frozen decision — importance tiering (PRD §12.5).** Resolve it this sprint
with measurement, not intuition. be1 implements two methods behind a flag
(mention count vs. scene participation + dialogue volume), measures both against
a hand-labelled tier list for two novels, and the retro records the winner.

---

## Scope

| Story | Owner | Summary |
|---|---|---|
| S3.1 | be1 | `pipeline.extract_characters` — pass-1 discovery, token-budgeted |
| S3.2 | be1 | Non-character rejection with stored reasons (F2.4) |
| S3.3 | be1 | Alias clustering cascade — normalise → nickname → embedding → LLM (F2.2) |
| S3.4 | be1 | Name-collision splitting — the two-Catherines guard |
| S3.5 | be1 | Character records, tiering (both methods), attribute extraction (F2.3) |
| S3.6 | be2 | Character read APIs — list, detail, mentions, with evidence |
| S3.7 | be2 | Manual merge/split endpoints with full mention re-pointing |
| S3.8 | be2 | Mention-context embeddings + the similarity service be1's cascade calls |
| S3.9 | be2 | Ontology prompt fragment + relation-extraction prompt prototype (Sprint 4 de-risk) |
| S3.10 | fe1 | Character list — tiers, alias chips, mention counts, first appearance |
| S3.11 | fe1 | Character detail — aliases with counts, mentions timeline, attributes, evidence |
| S3.12 | fe1 | Alias/mention inspector with page click-through to the viewer |
| S3.13 | do1 | Labelling harness — roster and alias ground truth for two novels |
| S3.14 | do1 | Extraction quality CI job — roster P/R/F1 and B³ reported per commit |
| S3.15 | do1 | GPU throughput + cost reporting for the extraction stage |

---

## Demo script (Day 5)

```bash
make up && make seed && make ingest BOOK=pride_and_prejudice
```

1. `/books/:id/characters` — roster within seconds of the stage completing.
2. Elizabeth Bennet appears **once**, with aliases `Elizabeth`, `Lizzy`, `Eliza`,
   `Miss Elizabeth Bennet`, `Miss Bennet` (context-dependent) — not five rows.
3. Tiers are sane: Elizabeth and Darcy protagonists; Mrs Reynolds minor;
   a one-line footman is `mentioned`.
4. Click Elizabeth → mentions timeline across chapters, first appearance page,
   attributes with evidence, every mention clicking through to its page.
5. `make ingest BOOK=wuthering_heights` → **Catherine Earnshaw and Catherine
   Linton are two rows.** This is the sprint's headline result.
6. `curl .../ops/extraction-quality` → roster P/R/F1 and B³ against ground truth.
7. Rejected candidates ("Netherfield", "Longbourn", "Providence") are listed
   with their reasons, not silently gone.

## Definition of Done

- [ ] Roster recall ≥ 95%, precision ≥ 90% on both labelled novels (F2.1)
- [ ] B³ F1 ≥ 0.85 on alias clustering (F2.2)
- [ ] **Two Catherines stay separate** — committed regression test
- [ ] Tiering method decided by measurement; decision recorded in `RETRO.md`
      and `traverse-prd.md` §12.5 updated
- [ ] Extraction stage cost and wall clock per novel recorded
- [ ] `RETRO.md` written

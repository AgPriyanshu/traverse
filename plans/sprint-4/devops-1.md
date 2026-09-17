# Sprint 4 · DevOps Engineer 1

**Branch:** `ai/do1/sprint-4-graph-ops` · **Worktree:** `../traverse-wt/do1`

## Mission

Measure the ship gate and make it recoverable. Two deliverables: a relation
quality harness that turns "the graph looks right" into numbers, and a proven
rebuild drill for Neo4j so a corrupted graph is a five-minute re-projection
rather than an incident.

## Owned paths

`eval/**`, `scripts/**`, `.github/workflows/**`, `api/ops/**`, `docker*`, `Makefile`

---

## S4.14 — Relation quality harness

Extend the Sprint 3 labelling tool to relationships. Label, for both gold
novels, **all major-character pairs** (protagonist + major tiers — labelling
every pair in a 60-character novel is 1,770 pairs and unnecessary):

```yaml
# eval/gold/pride_and_prejudice/relations.yaml
- subject: Elizabeth Bennet
  predicate: sibling_of
  object: Jane Bennet
  chapters: [1, 61]
  evidence_pages: [3, 12, 47]      # a sample, not exhaustive
```

Compute:

| Metric | Note |
|---|---|
| Per-predicate precision / recall / F1 | Aggregate hides that kinship is easy and adversarial is hard |
| **Citation page accuracy** | Sample 50 edges, check the cited page supports the claim (F3.2 ≥95%) |
| Spurious edge rate | Edges between pairs with no real relationship |
| Direction accuracy | `parent_of` reversed is a confident wrong answer, not a near miss |
| Temporal arc accuracy | Do transitions land in the right chapter |
| Evidence-free edge count | **Must be 0** — a structural invariant, assert it |

Citation accuracy needs human judgement on a sample. Extend the terminal
review tool: show the quote, the page, and the claim, and take y/n. Fifty
judgements is fifteen minutes and it is the number the whole product rests on.

*Acceptance:* `make eval-relations` produces the full table. Runs nightly; PRs
touching `api/relations/**` get the reduced one-novel version as a comment.

## S4.15 — Pass-2 cost and the rebuild drill

**Cost.** Pass 2 is the most expensive stage in the system. Report per book:
tokens in/out, **prefix-cache hit rate** (PRD §5.2's cost argument lives or dies
here — alert if it drops below 80%), chunks processed vs. skipped by be1's
prefilter, wall clock, USD at local-amortised and API rates.

Put pass-2 cost on the nightly trend from Sprint 2. A prompt change that halves
the cache hit rate should be visible the next morning, not in the Sprint 8 retro.

**Rebuild drill.** `make graph-rebuild BOOK=<id>`: `graph.reset(book_id)` →
re-project from Postgres → verify node and edge counts and a content checksum
match the pre-wipe state.

Run it in CI on the fixture book, and run it manually against a full novel this
sprint. PRD §5.5 claims "a corrupted graph is a re-upsert, never data loss" —
that claim needs to be tested before it is published, not after.

*Acceptance:* Rebuild produces an identical projection, verified by checksum, in
under 2 minutes for a 900-edge graph. Wired into `make test-integration`.

---

## DoD

- [ ] Relation quality table produced nightly and on relevant PRs
- [ ] Citation page accuracy measured on a human-judged sample of 50
- [ ] Evidence-free edge count asserted as 0 in CI
- [ ] Prefix-cache hit rate trended with an alert threshold
- [ ] Rebuild drill green in CI and proven on a full novel

# Sprint 8 · Backend Engineer 1

**Branch:** `ai/be1/sprint-8-gold` · **Worktree:** `../traverse-wt/be1`
**Owned:** `eval/gold/**`, `api/pipeline/**`, `api/extraction/**`

## Mission

Build the gold set. This is the least glamorous story in the project and the one
the whole credibility argument rests on — a weak eval set makes every number
meaningless, and a technical buyer will spot it faster than they spot a bug.

**Budget it honestly.** The PRD flags this: labelling two novels is real work.
It is most of your sprint. Do not let it get squeezed by something more
interesting.

---

**S8.4 Question set to 60+ (F6.1).** Extend Sprint 6's 30 questions to 60+,
across all six classes, for both gold novels. Each question carries: expected
answer, expected source pages, expected route, and expected abstention where it
applies.

Composition targets — a set that is 80% single-fact lookups reports a flattering
number that means nothing:

| Class | Count | Note |
|---|---|---|
| Single-fact | 12 | the easy baseline |
| Relationship | 15 | the core use case |
| Path / connection | 8 | multi-hop |
| Aggregation | 10 | exhaustiveness — exact set match |
| Temporal | 8 | "were they still friends by the end?" |
| **Unanswerable** | **10** | PRD §11: an eval set with no adversarial questions produces impressive numbers that mean nothing |

The unanswerable ten must be genuinely tempting — plausible relationships that
the novel never establishes, characters who sound like they should exist. A
question the model obviously cannot answer tests nothing.

**S8.5 Second novel fully labelled (F6.1).** *Wuthering Heights* to the same
depth as *Pride and Prejudice*: roster, aliases, tiers, major-pair relations with
page evidence, questions.

Wuthering Heights is the harder novel by design — two Catherines, nested
narration, a family tree spanning two generations. Labelling it properly is what
makes the eval credible rather than cherry-picked, and it is why the two-novel
set is not negotiable down to one.

Use do1's terminal labelling tool from Sprint 3. Verify every page reference
against the pinned corpus manifest — a page-number drift silently invalidates
every citation label.

## DoD

- [ ] 60+ questions, class distribution as specified, both novels
- [ ] Wuthering Heights labelled to full depth
- [ ] Every page reference verified against the corpus checksum
- [ ] Inter-annotator spot check on 10% — if you disagree with yourself a week
      later, the label is ambiguous and the question should be rewritten
- [ ] Gold set schema-validated in CI

# Sprint 8 · Backend Engineer 2

**Branch:** `ai/be2/sprint-8-evals` · **Worktree:** `../traverse-wt/be2`
**Owned:** `api/query/**`, `api/graph/**`, `api/relations/**`, `api/llm/**`, `api/eval/**`

---

**S8.1 Spoiler enforcement (F4.5).** The PRD is specific: enforced *at the query
layer*, not by asking the model nicely. Three places, all of which must hold:

1. **Graph** — filter edges on `first_chapter <= N` and nodes on
   `first_chapter <= N`. A character who first appears in chapter 20 does not
   exist at chapter 5.
2. **Retrieval** — filter chunks on chapter. The parameter has been plumbed since
   Sprint 2 for exactly this.
3. **Generation** — the model only ever sees filtered context. Nothing in the
   prompt references later chapters.

Make `chapter_lte` a **required field on the query context object**, not an
optional argument — `None` meaning "no limit" must be an explicit choice at the
call site. Optional spoiler filters get forgotten on one code path, and one path
is all it takes.

*Acceptance:* An automated leakage test asks 30 questions whose answers lie
beyond the limit and asserts zero post-limit content in answers, citations,
graph payloads, or character lists. **Zero, not low.**

**S8.2 Ablation switching (F6.3).** Every configuration axis becomes a runtime
config object, not a code branch: extraction passes, alias cascade depth,
retrieval arms, rerank on/off, graph-constraint on/off, model routing.

An eval run takes a config and records it in `eval_run.config`, so any published
number is reproducible from its row. A number in the table nobody can reproduce
is worse than no number.

**S8.3 Confidence calibration (F2.2).** Sprint 7's feedback store now holds
human corrections with the model's decision-time confidence. Fit a calibrator
(isotonic or Platt — try both, report both) mapping raw confidence to observed
accuracy.

Report **ECE before and after**. PRD F2.2 promises confidence that correlates
with correctness and improves as review volume grows; this is where that claim
gets its number. If the feedback volume is too small to calibrate meaningfully,
say so with the sample size rather than fitting noise and publishing it.

## DoD

- [ ] Leakage = 0 on the automated test across all four surfaces
- [ ] Every ablation axis switchable by config; every run reproducible
- [ ] ECE before/after with sample size stated
- [ ] `HANDOFF.md`: ablation config schema for do1's runner

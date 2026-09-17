# Sprint 8 — Evals & Spoiler Mode

**Goal:** the ablation table has real numbers in it, and the chapter slider
provably leaks nothing.

**PRD refs:** F6.1 – F6.4, F4.5 · Appendix A

> PRD F6: *"Non-optional. This is the credibility feature."* And §9.3: the
> ablation table is the single most valuable portfolio artifact. Everything
> built so far is the thing being measured; this sprint is the measurement, and
> it is what converts a technical buyer.

Much of the harness already exists — extraction quality from Sprint 3, relation
quality from Sprint 4, answer quality from Sprint 6. This sprint completes the
question set, runs the ablations, adds calibration, and ships the gate.

## Contract freeze (Day 1)

Migration `0013`: `eval_run`, `eval_result`, `calibration_model`.
`contracts/eval.py`: `AblationConfig`, `MetricSet`, `EvalRunOut`.
Query-layer: `chapter_lte` promoted from optional parameter to **required
context** on every graph and retrieval call path.

## Scope

| Story | Owner | Summary | PRD |
|---|---|---|---|
| S8.1 | be2 | Spoiler enforcement at the query layer — graph, retrieval, generation | F4.5 |
| S8.2 | be2 | Ablation config switching — one run, N configurations | F6.3 |
| S8.3 | be2 | Confidence calibration from Sprint 7's feedback store; ECE reported | F2.2, F6.2 |
| S8.4 | be1 | Gold question set to 60+, all six classes, with expected citations | F6.1 |
| S8.5 | be1 | Second novel fully labelled — relations and questions | F6.1 |
| S8.6 | fe1 | Chapter slider with live graph and answer scoping | F4.5 |
| S8.7 | fe1 | Eval results view — ablation table, per-metric drill-down | F6.3 |
| S8.8 | do1 | Ablation runner — the full matrix, reproducible, cached | F6.3 |
| S8.9 | do1 | CI regression gate: −2 points fails the PR | F6.4 |
| S8.10 | do1 | Publish the table to the repo README, auto-updated from the last run | §9.4 |

## The ablation matrix (PRD Appendix A)

**Extraction:** single-pass vs two-pass × string-only vs full alias cascade,
plus a with-human-review row.
**Retrieval:** vector-only → +BM25 → +rerank → +graph-constrained.
**Model:** Qwen3-8B local → frontier API → routed.

Do not run the full cross product — it is 30+ full-novel runs and most cells are
uninteresting. Run each axis against the recommended configuration of the others,
plus the recommended row itself. Say in the writeup that this is what you did;
a partial matrix honestly described beats a full one nobody believes.

## Demo script

1. `/books/:id/graph` with the slider at chapter 5 → the graph visibly shrinks;
   nothing from chapter 6+ is present as node, edge, or citation.
2. "What happens between Elizabeth and Darcy?" at chapter 5 → an answer true to
   chapter 5, with no hint of the ending.
3. `make eval-all` → the full table, every cell populated.
4. Two-pass beats single-pass by a stated margin; graph-constrained beats
   vector-only by a stated margin. **If either does not, that is the finding and
   it gets published** — the PRD commits to this.
5. Calibration curve: high-confidence extractions are measurably more accurate,
   with ECE before and after calibration.
6. Open a PR degrading retrieval → CI fails with the metric delta.

## Definition of Done

- [ ] **Spoiler leakage rate = 0** — measured, not asserted (F4.5)
- [ ] 60+ gold questions across all six classes, two novels labelled
- [ ] Every Appendix A cell populated with a real number
- [ ] ECE reported before and after calibration
- [ ] Regression gate live and demonstrated failing
- [ ] Table published in the README
- [ ] `traverse-prd.md` Appendix A updated with the real numbers
- [ ] `RETRO.md` written

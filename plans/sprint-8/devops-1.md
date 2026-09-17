# Sprint 8 · DevOps Engineer 1

**Branch:** `ai/do1/sprint-8-ablations` · **Worktree:** `../traverse-wt/do1`
**Owned:** `eval/**`, `scripts/**`, `.github/workflows/**`, `api/ops/**`, `docker*`

---

**S8.8 Ablation runner (F6.3).** Take a matrix of configurations and produce the
table. Requirements that separate a usable runner from a one-off script:

- **Cache aggressively.** Parsing, chunking, and embedding are identical across
  most configurations — re-ingesting a novel per cell turns a 2-hour run into 20.
  Key the cache on the config fields that actually affect the stage.
- **Resumable.** A 3-hour run that dies on cell 22 must not restart at cell 1.
- **Reproducible.** Every run records its config, corpus checksum, git SHA, and
  model versions. A number in the published table must be regenerable a month
  later, or it should not be published.
- **Honest about partial matrices.** The runner records which cells were run and
  which were skipped, and the published table marks the difference rather than
  leaving a blank that reads as zero.

Run the full matrix on the GPU host overnight. Cost per full matrix goes in the
retro — this is the most expensive recurring job in the project.

**S8.9 Regression gate (F6.4).** The PRD's rule: a PR dropping answer accuracy
more than 2 points fails. Extend it to relation F1 and citation precision, which
are equally load-bearing.

Use the reduced one-novel set on PRs to keep the loop under 10 minutes; the full
set runs nightly and on `ai-master`.

Two things make a gate survive contact with reality: a **documented override**
(a label plus a written justification recorded in the PR, for a deliberate
trade-off) and **noise awareness**. Measure run-to-run variance on an unchanged
commit first — if variance is ±1.5 points, a 2-point gate is a coin flip and will
be disabled within a week. Report the variance in the retro and set the threshold
from it.

**S8.10 Publish the table (§9.4).** Auto-generate the README's results section
from the latest full run: the ablation table, the headline metrics, the corpus
and gold-set version, and the run date. PRD §9.4 wants the eval results above the
fold in the public repo, and a hand-maintained table goes stale in a fortnight.

## DoD

- [ ] Full matrix runs overnight, cached, resumable, reproducible
- [ ] Run-to-run variance measured **before** the gate threshold is set
- [ ] Gate live, demonstrated failing, with a documented override path
- [ ] README table auto-generated from the last full run
- [ ] Cost per full matrix recorded

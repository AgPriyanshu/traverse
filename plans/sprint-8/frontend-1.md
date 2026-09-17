# Sprint 8 · Frontend Engineer 1

**Branch:** `ai/fe1/sprint-8-spoiler` · **Worktree:** `../traverse-wt/fe1`
**Owned:** `web/src/**`, `web/tests/**`

## Design input

Read [design/DESIGN.md](../../design/DESIGN.md); implement the
`spoiler-control` artboard. Load the `dataviz` skill before building S8.7 — the
ablation table and calibration chart are the portfolio's most-screenshotted
surfaces and they must read as one system.

---

**S8.6 Chapter slider (F4.5).** A persistent control in the book shell: "I've
read up to chapter ___". It scopes **everything** — graph, characters, answers,
citations.

Make the effect visible. When the slider moves, the graph animates to its new
state so the user sees nodes and edges leave. That animation is the feature: it
is what makes a reader trust that the system is actually protecting them rather
than claiming to.

Persist per book in `localStorage` — a reader's position is per-viewer, not
shared state. Default: the book's last chapter (no limit), because most users
come having finished the book, and a spoiler guard that gets in their way on
first load is an annoyance.

Show the active limit unmistakably wherever scoped content appears — a quiet
banner on the graph and ask screens. A user who forgets the slider is set to
chapter 5 will read an incomplete answer as a wrong one.

**S8.7 Eval results view (F6.3).** `/ops/evals` — the ablation table rendered as
a real comparison, with the recommended configuration marked, deltas against
baseline shown, and each cell drilling into its per-question results.

Also: the calibration curve (predicted confidence vs. observed accuracy, with
the diagonal), and the metric trend over runs.

This screen is a portfolio artifact in its own right — a buyer who sees a live,
drillable ablation table understands immediately that the numbers are real and
not a README claim. Build it to be screenshotted.

## DoD

- [ ] Slider scopes every surface; nothing beyond the limit is reachable in the UI
- [ ] The graph visibly animates to its scoped state
- [ ] Active limit always discoverable when it is not the default
- [ ] Ablation table drills to per-question results
- [ ] Calibration chart accessible — the diagonal labelled, not just drawn

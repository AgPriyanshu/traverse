# Sprint 9 · Frontend Engineer 1

**Branch:** `ai/fe1/sprint-9-polish` · **Worktree:** `../traverse-wt/fe1`
**Owned:** `web/src/**`, `web/tests/**`

## Design input

Read [design/DESIGN.md](../../design/DESIGN.md); implement `ops-dashboard`.
Load the `dataviz` skill before the cost and latency charts — this dashboard is
the demo's closing argument and it has to look like one system, not five chart
libraries. S9.12 is also the sprint where the design system gets audited against
what actually shipped; discrepancies are DCRs, not silent divergence.

---

**S9.10 Ops dashboard (F7.1–7.4).** Four panels: cost, performance, pipeline
health, and routing control.

The **routing control is the centrepiece**. Per-purpose model selection, applied
live, with cost per query and accuracy delta from the latest eval **side by side
and updating**. The user must see the trade-off in one glance; a settings form
with a save button throws the whole point away.

Charts: cost by stage (stacked), latency by stage (p50/p95/p99), throughput and
queue depth over time, cost-per-query trend annotated with policy changes. That
last annotation is what makes the chart an argument rather than a picture.

**S9.11 Inference-mode labelling (ETH-4, NFR-residency).** Wherever a query may
leave the machine, say so — unmissably but not alarmingly. A persistent indicator
of the current mode, and an explicit consent step before a private upload is ever
routed to an API.

PRD §6 asks that zero-egress be *visibly verifiable*. This is the UI half of it;
do1's dashboard is the other.

**S9.12 Responsive and accessibility pass (NFR-a11y).** Every screen at 400px.
Keyboard-complete everywhere. Contrast ≥4.5:1 in both themes, verified with a
tool. Screen-reader pass on the review queue and the graph's list view — the two
places where the interaction is complex enough to break.

Run an automated audit (axe) in CI and fix what it finds. It will not catch
everything, but the things it catches are the embarrassing ones, and the PRD
promises this demo gets opened on a phone by someone skimming profiles.

**S9.13 Public landing state (§9.1).** No signup. Three suggested questions on
the seeded corpus so a skimming visitor gets value in one click. The seeded
corpus is visibly read-only; the upload path leads to a clearly-labelled sandbox
with its quota stated up front, not discovered on rejection.

## DoD

- [ ] Routing control shows both deltas live, in one view
- [ ] Inference mode always discoverable; consent required before any egress
- [ ] Every screen 400px-clean, keyboard-complete, contrast-verified
- [ ] axe audit in CI, passing
- [ ] Landing state delivers an answer in one click

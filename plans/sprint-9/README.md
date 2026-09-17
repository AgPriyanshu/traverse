# Sprint 9 — Ops, Hardening & Go-to-Market

**Goal:** the ops dashboard proves production experience, the demo is publicly
reachable, and the writeup is published.

**PRD refs:** F7.1 – F7.4 · §9, §10 · NFR-residency, NFR-a11y, ETH-1..4

> PRD F7.3: the routing control screen *"is the demo's closing argument — it is
> what proves production experience rather than tutorial experience."*

## Contract freeze (Day 1)

Migration `0014`: `routing_policy`, `cost_snapshot`, `upload_session` (for
demo-upload quota and TTL). `contracts/ops.py`: `MetricsOut`, `RoutingPolicy`,
`CostBreakdown`.

## Scope

| Story | Owner | Summary | PRD |
|---|---|---|---|
| S9.1 | do1 | Cost telemetry by stage and query, rolling spend | F7.1 |
| S9.2 | do1 | Performance telemetry — latency by stage, TTFT, GPU/KV, queue depth | F7.2 |
| S9.3 | do1 | Pipeline health — run history, failure rates, dead-letter, trace links | F7.4 |
| S9.4 | do1 | Public deploy — CPU profile, API inference, TLS, rate limits | §9.1 |
| S9.5 | do1 | Demo hardening — public-domain-only guard, upload quota + 24h TTL | ETH-1, §12.3 |
| S9.6 | be2 | Routing policy engine — per-purpose model selection, live switching | F7.3 |
| S9.7 | be2 | Frontier API path for `adjudicate` / `answer` / `judge` with fallback | §5.1 |
| S9.8 | be1 | Upload privacy — per-session isolation, deletion, no pooling | ETH-2 |
| S9.9 | be1 | OCR path for scanned PDFs (if Sprint 8 left room; else formally deferred) | §3.2 |
| S9.10 | fe1 | Ops dashboard — cost, latency, health, with the routing control | F7.1-7.4 |
| S9.11 | fe1 | Inference-mode labelling in the UI wherever a query leaves the machine | ETH-4, NFR-residency |
| S9.12 | fe1 | Responsive and accessibility pass across every screen | NFR-a11y |
| S9.13 | fe1 | Public landing state — three suggested questions, read-only corpus | §9.1 |
| S9.14 | all | The 90-second recording, per the PRD's shot list | §9.2 |
| S9.15 | orch | Engineering writeup — "Why two-pass extraction, with numbers" | §9.3 |

## The closing-argument screen (F7.3)

The routing control is not a settings page. Flipping a policy must visibly move
**both** numbers at once — cost per query down, accuracy delta from the live eval
scores — side by side. A buyer who sees a builder trade 3 accuracy points for an
80% cost reduction, *and show the trade*, is looking at production experience.

Acceptance from the PRD: flipping the policy changes observed cost per query
measurably **within the same session**.

## Demo script — the portfolio walkthrough

1. Public URL, no signup. Landing offers three questions on *Pride and Prejudice*.
2. Ask one → cited answer → click a citation → the page.
3. Graph explorer, filter to kinship, drag the spoiler slider back — the graph
   shrinks.
4. Review queue: the two Catherines, resolved by a human, cascading.
5. Ops dashboard: cost per book fully local vs. routed; flip the policy and watch
   both numbers move.
6. `docker compose up` on a fresh machine → working system in under 5 minutes.
7. README: the ablation table above the fold.

## Definition of Done

- [ ] Public demo reachable, no signup, working on a phone, rate-limited
- [ ] Ops dashboard live with real cost, latency, and health
- [ ] Routing policy switchable live with both deltas visible
- [ ] Public corpus is public-domain only, enforced in code and documented (ETH-1)
- [ ] Uploads private, deletable, API-routing labelled (ETH-2, ETH-4)
- [ ] Every screen responsive to 400px, keyboard-complete, ≥4.5:1 contrast
- [ ] 90-second recording cut; writeup published; README complete
- [ ] `traverse-prd.md` updated: §12 open decisions resolved, real numbers in
      §1.3 and Appendix A
- [ ] **Final `RETRO.md`** — plus a project-level retrospective across all eight

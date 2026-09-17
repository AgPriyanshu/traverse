# Sprint 6 · DevOps Engineer 1

**Branch:** `ai/do1/sprint-6-answers` · **Worktree:** `../traverse-wt/do1`
**Owned:** `eval/**`, `scripts/**`, `.github/workflows/**`, `api/ops/**`, `docker*`

## Mission

Make answer quality and latency continuously measured. Sprint 8 publishes these
numbers; this sprint makes them exist and trend.

---

**S6.14 Answer quality harness (F6.2 groundwork).** Build the question set
tooling and a first 30 questions across the PRD's classes — single-fact,
relationship, path, aggregation, temporal, unanswerable. Sprint 8 grows it to
60+; starting now means Sprint 8 is scoring, not authoring.

Metrics: answer accuracy (LLM-judge with a **frontier** model — do not let the
system grade its own homework with the same 8B that wrote the answer, and spot
check 20% by hand), citation precision (is the cited page supporting), abstention
rate on unanswerable, aggregation completeness (exact set match).

Judge prompts are versioned and committed. A changed judge prompt invalidates
historical comparisons, so treat it like a schema.

*Acceptance:* `make eval-answers` produces the table; nightly trend posted.

**S6.15 Latency budgets in CI.** From be1's `query_log.latency_ms`: p50/p95/p99
per stage, TTFT distribution, and the breakdown of where the 6s budget goes.

Add a **performance smoke test** to the merge train: 20 fixture questions against
the fixture book, failing the build if p95 exceeds 6s or TTFT exceeds 1.5s (PRD
NFR-perf). Run it on the integration host only — per BRANCH.md §9, timings from a
worktree sharing the GPU are meaningless and must not gate anything.

Trend cost per query alongside latency. A change that improves latency by routing
to a frontier API is not a free win, and the dashboard should make that visible.

*Acceptance:* Performance gate wired into the merge train, with a documented
path to waive it for an unrelated hotfix.

## DoD

- [ ] 30-question set committed and scoring nightly
- [ ] Judge prompts versioned; 20% human spot check done once this sprint
- [ ] Latency gate live on the integration host
- [ ] Cost-per-query trended next to latency

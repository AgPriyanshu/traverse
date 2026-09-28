# Sprint 8 Retrospective

**Dates:** 2026-09-28
**Goal:** the ablation table has real numbers in it, and the chapter slider provably leaks nothing.
**Outcome:** Spoiler leakage is genuinely solved — measured, not asserted. The ablation table is honestly partial: real numbers where a config-switch and a metric exist, clearly marked `blocked`/`not measured this sprint` everywhere one doesn't, rather than fabricated.

## 1. Delivered

| Story | Owner | Status | Notes |
|---|---|---|---|
| S8.1 | be2 | Built, merged, verified | `ReadingScope` — a required-everywhere value object — closes real spoiler leaks across relation/path/neighbourhood/arc/evidence lookups that had **no reading-position parameter at all** before this sprint, not just a forgettable optional one. Measured 0/22 leakage checks. |
| S8.2 | be2 | Built, merged, verified | Ablation config switching for the retrieval axis (vector_only → bm25 → rerank → graph_constrained) and model axis (local/frontier/routed). Extraction axis explicitly out of scope — `resolve()` raises rather than silently no-opping. |
| S8.3 | be2 | Built, merged, verified (mechanism only) | Calibration (reliability diagram, Platt scaling, isotonic regression, pure Python) verified against synthetic data. Zero real `CorrectionFeedback` rows exist anywhere in this environment — Sprint 7's review queue has never been exercised by a real reviewer here — so real ECE is undefined, honestly reported as `fitted_on_n=0` rather than fabricated. |
| S8.4–S8.5 | be1 | Built, merged, verified | Gold question set grown to 63 across both novels, matching the sprint's per-class composition table exactly (single_fact 12, relationship 15, path 8, aggregation 10, temporal 8, unanswerable 10). Wuthering Heights fully labelled (29 relations, 25 questions) against a re-verified corpus build, not recalled from memory. |
| S8.6–S8.7 | fe1 | Built, merged, verified live | Persistent reading-position slider, verified in a live test to actually shrink the rendered graph as it moves (not just send the right API parameter). Eval results view built against frozen contracts, with fixture data clearly labelled as such since no live backend route existed yet when the story was built. |
| S8.8–S8.10 | do1 | Built, merged, verified, then extended | Ablation runner, regression gate (demonstrated failing on real degraded data), README auto-publish — plus a same-day fast-follow once be2's S8.2 merged, wiring the retrieval/model axes to real independent measurement instead of all sharing one run. |

**Demo result:** Not run as a single live end-to-end pass (no fresh chapter-5-scoped Q&A recorded against a real book in one sitting). Each demo-script beat was verified independently — the spoiler slider's live shrink test, the 0/22 leakage suite, and the regression gate's real failing run are the closest equivalents.

## 2. Measured (real infra, real data, no mocked metrics)

| DoD line item | Status | Evidence |
|---|---|---|
| **Spoiler leakage rate = 0** — measured, not asserted (F4.5) | **Met** | `api/tests/query/test_spoiler_leakage.py`, 0/22 checks across roster, character detail, whole-project graph, neighbourhood, shortest path, relationship-lookup/aggregation templates, relation arc, evidence, and dense/lexical retrieval. Two real leaks were found and fixed while building the harness (Neo4j's denormalized `page_refs` leaking future citation pages on an already-visible edge; an aggregation answer sentence built from unfiltered Cypher rows). |
| 60+ gold questions across all six classes, two novels labelled | **Met** | 63 questions (38 Pride and Prejudice + 25 Wuthering Heights), exact per-class composition match, both validated against `eval/loaders.py`'s JSON schema. |
| Every Appendix A cell populated with a real number | **Not met, honestly partial** | 2 measured, 1 partial, 10 blocked of 13 rows as of the last run (`README.md`, auto-generated). Extraction's recommended row is real (P&P F1 0.701, n=52; Wuthering Heights F1 0.642, n=23). Retrieval and model axes now run independently (do1's fast-follow) but every accuracy/citation-precision number is `blocked` on a frontier judge key that isn't configured in this environment, and `traverse-prd.md`'s original column set (Coref B³ F1, Recall@5/20, MRR, p95 latency) was never wired into the ablation `MetricSet` this sprint — see §3 and the updated Appendix A for the exact accounting. |
| ECE reported before and after calibration | **Met, on synthetic data only** | `ece_before=0.200`, `ece_after=0.000` (isotonic) / `0.083` (Platt) — the mechanism is real and tested, but there is no real `CorrectionFeedback` data anywhere in this environment to fit it on. This is a real gap: Sprint 7 shipped the review queue but it has never been used by an actual reviewer here, so Sprint 8's calibration has nothing real to calibrate against. |
| Regression gate live and demonstrated failing | **Met** | do1 pulled live Pride and Prejudice numbers, degraded `relation_f1` to simulate a bad PR, and confirmed `check_regression_gate.py` reports the delta and exits 1 — a real failure, not a unit test of the comparison logic alone. |
| Table published in the README | **Met** | Auto-generated, idempotent marker-splicing, regenerated twice this sprint (do1's original run, then the fast-follow) with real timestamps and git SHAs. |
| `traverse-prd.md` Appendix A updated with the real numbers | **Met, with the same honesty as the README** | Updated by the orchestrator after the merge train; every blocked/unmeasured cell says why rather than being left blank as if forgotten. |
| `RETRO.md` written | Met | This file. |

## 3. Why the ablation table is still mostly blocked, and what actually closes it

This is not a case of running out of time on a straightforward task — three independent, structural gaps compound:

1. **No frontier judge key is configured in this environment** (`FRONTIER_MODEL`/`FRONTIER_API_KEY` are blank in `.env` by design — no egress path exists without a human supplying a real key). Every answer-accuracy and citation-precision number, across every axis, is gated on this. This is not a code fix; it needs the user to provision a real key.
2. **No extraction-mode switch was built this sprint.** be2's S8.2 explicitly scoped out the extraction axis (`resolve()` raises `AblationAxisNotOwned` rather than silently no-opping) because no story this sprint owned building single-pass/two-pass or alias-cascade toggling. The extraction axis's recommended row (the pipeline's one real configuration) is measured; every other row on that axis is blocked for a structural reason, not a bug.
3. **The ablation `MetricSet` only wires precision/recall/F1/accuracy**, not the PRD's originally-sketched Recall@5/Recall@20/MRR/p95-latency/cost-per-book/ingest-time columns. This is a real design gap from when the contract was frozen at Sprint 8's Day 1 — those columns were aspirational in the original PRD table and nobody's story this sprint included building the instrumentation to fill them.

None of these are things an agent worked around by fabricating a number — every blocked cell says exactly why, in both `README.md` and the updated PRD Appendix A. **Recommend Sprint 9 (or a dedicated pre-launch pass) explicitly scope**: (a) provisioning a real frontier API key, (b) building the extraction-mode switch, (c) wiring the remaining metrics into `MetricSet`, if the ablation table is meant to be the complete artifact the PRD's own framing calls it ("the single most valuable portfolio artifact").

## 4. Real bugs found and fixed this sprint

1. **Four graph read paths had no reading-position parameter at all** (be2, S8.1): `relations_out`, `relation_arc`, `shortest_path`, `get_neighbourhood`, `list_evidence`, and the `relationship_lookup`/`aggregation` Cypher templates returned the whole project regardless of where the reader actually was. This was the real spoiler-leak vector, not the "forgot to pass `None`" framing the sprint plan assumed going in.
2. **Neo4j's denormalized `page_refs` edge property leaked future citation pages** even on an edge that was itself already visible at the current reading position (be2, found while building the leakage harness).
3. **An aggregation answer's own sentence was built from unfiltered Cypher rows**, not the scope-filtered relation list — a second, independent leak path on the same feature (be2).
4. **`api/tests/conftest.py` was missing the Sprint 8 tables from its truncate list** (be2) — a fitted calibration model's version number climbed across test runs because nothing reset it between them.
5. **`.env.example`'s `VLLM_BASE_URL=http://localhost:8080/v1/` doesn't resolve from inside the `api` container** (do1, found running the ablation fast-follow for real) — every LLM call 500'd until fixed.
6. **A real `greenlet_spawn has not been called` error in `api/query/pipeline.py::_finish`**, raised on every query route in this environment during the answer-persistence stage, after the answer itself is already correctly captured (do1, found running the ablation fast-follow against the live pipeline for real; be2-owned, not fixed this sprint — flagged in `plans/sprint-8/HANDOFF.md` as a live production bug, not a test artifact).
7. **No timeout exists anywhere in `api/llm/**`** — do1 hit a single generation call run past three minutes uncapped while measuring the ablation matrix live, and added a 90-second per-question timeout to the harness itself since none exists in the LLM client layer. Worth a real fix in `api/llm/**`, not just a harness workaround.

## 5. Process notes

- **Cross-agent dependency handled well without idle waiting**: fe1 (S8.6) needed be2's S8.1 contract shape; do1 (S8.8) needed be2's S8.2 config-switch. Both checked be2's in-progress worktree directly rather than blocking, built against the frozen contract or documented what was still missing, and both correctly re-synced once be2 landed (fe1 via a documented follow-up note, do1 via an explicit fast-follow branch after the main merge train). This is the pattern to keep using — read the other agent's actual code when it exists, don't wait idle on a HANDOFF.md that hasn't been written yet.
- **The Sprint 8 freeze under-specified the ablation `MetricSet`'s actual field list** relative to the PRD's original Appendix A column sketch (§3.3). Worth catching this kind of contract/PRD drift at freeze time in future sprints — a quick diff between what the contract types actually carry and what the PRD table headers ask for would have surfaced this before three agents built against the narrower shape.
- Same fragile-vocabulary pattern from Sprint 7 (`ReviewResolution.decision` as a free string) did not recur this sprint — no new instance of two agents needing to independently agree on an under-specified wire shape.
- do1's fast-follow (§ummary in `plans/sprint-8/HANDOFF.md`, "S8.8.1") is a good template for handling a cross-story dependency that resolves *after* the main merge train: cut a new branch from the merged result, do the narrow wiring, verify, merge again — rather than either blocking the whole sprint's close on it or leaving the gap undocumented.

## 6. Carried into Sprint 9 / a pre-launch pass

- Provision a real `FRONTIER_MODEL`/`FRONTIER_API_KEY` — this is the single blocker on the largest number of DoD line items (answer accuracy, citation precision, real calibration ECE) and is not something an agent can do on its own.
- Build an extraction-mode switch (single-pass/two-pass, alias-cascade toggle) if the extraction axis of Appendix A is meant to be fully populated.
- Wire Recall@5/Recall@20/MRR/p95-latency/cost-per-book/ingest-time into `api/eval/ablation.py`'s `MetricSet`.
- Fix the `greenlet_spawn` error in `api/query/pipeline.py::_finish` (be2) — a real bug in the live query path, found under real load, not a test-only issue.
- Add a timeout somewhere in `api/llm/**` — none exists today at the client layer.
- Get Sprint 7's review queue exercised by a real reviewer against real data, so Sprint 8's calibration mechanism has something real to fit on.

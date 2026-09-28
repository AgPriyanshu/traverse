# Sprint 8 — do1 HANDOFF

## What landed (S8.8, S8.9, S8.10)

- `eval/ablation.py` + `scripts/run_ablation.py` (`make eval-ablation`) —
  the partial Appendix A matrix, cached, resumable, writes `EvalRun`/
  `EvalResult` (migration 0011) and `eval/ablation_runs/latest.json`.
- `api/ops/ablation.py` behind `GET /ops/eval-runs/latest` and
  `GET /ops/eval-runs/{run_id}` — read this, fe1, for S8.7's table rather
  than the JSON artifact; it's the durable, queryable copy.
- `eval/regression_gate.py` + `scripts/{collect_gate_metrics,check_regression_gate}.py`
  (`make regression-gate`) + `.github/workflows/regression-gate.yml` — the
  CI gate, demonstrated failing on real data (see below).
- `scripts/publish_ablation_readme.py` (`make eval-ablation-readme`) —
  README.md's ablation table, regenerated from the last run.

## Two real environment gaps — not silently worked around

**No frontier judge key.** `FRONTIER_MODEL`/`FRONTIER_API_KEY` are blank in
every `.env` this sprint (by design — no key has been provisioned). Every
call to `LLMPurpose.JUDGE` (`api/ops/answer_judge.py`) requires
`settings.frontier_model`, and `api/llm/routing.py::route_for` refuses it
outright rather than silently grading with the local model. Practical effect:

- Answer **accuracy** and **citation precision** report `None`, never a
  fabricated number, for every cell — verified against a real, partial S6.14
  run already sitting in the shared integration stack (19/30 Pride and
  Prejudice gold questions answered, `judge: null` on every row).
- **Abstention rate** and **aggregation exact-match** need no judge and
  *are* real numbers from that same run — aggregation exact-match is 0/4,
  which is a genuine finding (`pp-016`–`pp-019` in the gold set), not a
  placeholder. Worth a look before Sprint 9: the aggregation path is
  currently failing every gold aggregation question it has answered so far.
- **Whoever provisions a real frontier key** can re-run `make eval-ablation`
  and `make eval-answers BOOK=pride-and-prejudice` (finishing the remaining
  11/30 questions first) to get real accuracy/citation-precision numbers —
  no code change is needed, this starts asserting for real the moment the
  key exists, same pattern as every prior sprint's "not my dependency" gaps.

**be2's S8.2 (ablation config-switch) had not landed as of this run** — I
checked `../traverse-wt/be2` directly (clean tree, only the freeze commit)
rather than wait idle, per my brief. The pipeline can currently produce
exactly **one** configuration (two-pass extraction, full alias cascade,
graph-constrained retrieval, local-routed-to-vLLM model), so:

- The extraction axis's non-recommended rows (single-pass, string-only
  aliases, +human-review) are all `blocked: no ablation config-switch exists`.
- The retrieval axis's non-recommended rows (vector-only, BM25, rerank) are
  blocked the same way.
- The model axis's frontier/routed rows are blocked for a *second*,
  independent reason: `api/llm/routing.py::route_for` routes every
  non-`judge` purpose to local vLLM unconditionally — there is no frontier or
  routed answering path to switch *to* yet, regardless of a key.
- Retrieval's and model's "recommended" cells are consequently **the same
  live run**, not independently measured — there's currently no way to tell
  "graph-constrained retrieval quality" apart from "local model quality"
  because nothing yet varies one without the other.

**If S8.2 lands a config-switch entry point before this branch merges**, the
hook I need is small: something `scripts/run_ablation.py` can call per cell
before ingesting/querying — e.g. a context manager or a settings override
resolvable from an `AblationConfig` — to actually produce the alternate
configuration. Ping me (do1) or file the shape in this doc and I'll wire
`measure_extraction_cell`/`measure_answer_backed_cell` to it; the matrix
definition and caching/resumability don't need to change, only which cells
are marked `blocked_reason=None`.

## Variance — not measured this sprint

devops-1.md asks for run-to-run variance on an unchanged commit *before*
setting the gate threshold. I did not measure it: extraction/relation
quality against already-ingested data is a deterministic read (zero variance
by construction, not informative), and measuring real noise on
accuracy/citation precision needs repeated end-to-end runs through the LLM
pipeline *and* the frontier judge — the latter is the gap above, and the
former is the "GPU host overnight" cost the sprint plan already flags as the
most expensive recurring job in the project. The gate ships at the PRD's
stated 2-point threshold, unvalidated against this project's own noise.
**Retro action item:** once a frontier key exists, run the full ablation
matrix 3-5 times on an unchanged `ai-master` commit and set the threshold
from the observed spread rather than the PRD's default.

## For the orchestrator

`traverse-prd.md` Appendix A is orchestrator-owned (BRANCH.md) and out of
do1's edit scope. The real numbers now live in README.md's generated section
(same source, `eval/ablation_runs/latest.json`) — copy them across, or point
Appendix A at the README section instead of duplicating it by hand.

## Cost

Not measured this sprint. The full matrix currently only has one measurable
configuration per axis (see above), so a "cost per full matrix" number would
describe the same one run three times, not the sweep the DoD asks for. Once
S8.2 lands, re-run `make eval-ablation` and report the wall clock/cost from
that — `scripts/run_ablation.py`'s cache/resumability means a second run
against unchanged cells costs nothing, so the number to report is the first
cold run's.

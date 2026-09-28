import type { AblationConfig, CalibrationModelOut, EvalResultOut, EvalRunOut, MetricSet } from "./types";

/**
 * Realistic placeholder numbers matching the frozen contract shapes exactly
 * (`EvalRunOut`/`EvalResultOut`/`AblationConfig`/`MetricSet`/
 * `CalibrationModelOut`), stood in for do1's ablation runner (S8.8) and be2's
 * calibration fit (S8.3), neither of which has a live route yet. **Every
 * number here is invented for layout and interaction — none of it is a real
 * measurement.** Swap `latestRun`/`calibration` for a real fetch the moment
 * one exists; `plans/sprint-8/HANDOFF.md` names the exact call sites.
 */

const metrics = (overrides: Partial<MetricSet>): MetricSet => ({
  precision: null,
  recall: null,
  f1: null,
  accuracy: null,
  ece: null,
  spoiler_leakage_rate: null,
  sample_size: 0,
  ...overrides,
});

const extractionConfig = (overrides: Partial<AblationConfig>): AblationConfig => ({
  axis: "extraction",
  label: "",
  extraction_mode: null,
  alias_mode: null,
  with_human_review: false,
  retrieval_mode: null,
  model_mode: null,
  ...overrides,
});

const retrievalConfig = (overrides: Partial<AblationConfig>): AblationConfig => ({
  ...extractionConfig({}),
  axis: "retrieval",
  ...overrides,
});

const modelConfig = (overrides: Partial<AblationConfig>): AblationConfig => ({
  ...extractionConfig({}),
  axis: "model",
  ...overrides,
});

/** Extraction-axis rows, everything else held at the recommended retrieval/model configuration. */
const extractionResults = (runId: string, scale: number): EvalResultOut[] => [
  {
    id: `${runId}-ext-1`, eval_run_id: runId, axis: "extraction",
    label: "Single-pass, string-only alias matching", book_key: "pride-and-prejudice",
    config: extractionConfig({ extraction_mode: "single_pass", alias_mode: "string_only", label: "single-pass/string-only" }),
    metrics: metrics({ precision: 0.71 * scale, recall: 0.58 * scale, f1: 0.638 * scale, sample_size: 214 }),
  },
  {
    id: `${runId}-ext-2`, eval_run_id: runId, axis: "extraction",
    label: "Single-pass, full alias cascade", book_key: "pride-and-prejudice",
    config: extractionConfig({ extraction_mode: "single_pass", alias_mode: "full_cascade", label: "single-pass/full-cascade" }),
    metrics: metrics({ precision: 0.74 * scale, recall: 0.69 * scale, f1: 0.714 * scale, sample_size: 214 }),
  },
  {
    id: `${runId}-ext-3`, eval_run_id: runId, axis: "extraction",
    label: "Two-pass, string-only alias matching", book_key: "pride-and-prejudice",
    config: extractionConfig({ extraction_mode: "two_pass", alias_mode: "string_only", label: "two-pass/string-only" }),
    metrics: metrics({ precision: 0.85 * scale, recall: 0.74 * scale, f1: 0.791 * scale, sample_size: 214 }),
  },
  {
    id: `${runId}-ext-4`, eval_run_id: runId, axis: "extraction",
    label: "Two-pass, full alias cascade", book_key: "pride-and-prejudice",
    config: extractionConfig({ extraction_mode: "two_pass", alias_mode: "full_cascade", label: "two-pass/full-cascade" }),
    metrics: metrics({ precision: Math.min(0.94 * scale, 0.99), recall: Math.min(0.89 * scale, 0.97), f1: Math.min(0.914 * scale, 0.98), sample_size: 214 }),
  },
  {
    id: `${runId}-ext-5`, eval_run_id: runId, axis: "extraction",
    label: "Two-pass, full alias cascade + human review", book_key: "pride-and-prejudice",
    config: extractionConfig({ extraction_mode: "two_pass", alias_mode: "full_cascade", with_human_review: true, label: "two-pass/full-cascade/reviewed" }),
    metrics: metrics({ precision: Math.min(0.98 * scale, 0.995), recall: Math.min(0.96 * scale, 0.99), f1: Math.min(0.97 * scale, 0.99), sample_size: 214 }),
  },
];

/** Retrieval-axis rows, extraction/model held at their recommended configuration. */
const retrievalResults = (runId: string, scale: number): EvalResultOut[] => [
  {
    id: `${runId}-ret-1`, eval_run_id: runId, axis: "retrieval",
    label: "Vector-only (dense pgvector)", book_key: "pride-and-prejudice",
    config: retrievalConfig({ retrieval_mode: "vector_only", label: "vector-only" }),
    metrics: metrics({ accuracy: 0.61 * scale, spoiler_leakage_rate: 0, sample_size: 62 }),
  },
  {
    id: `${runId}-ret-2`, eval_run_id: runId, axis: "retrieval",
    label: "+ BM25 lexical, RRF fused", book_key: "pride-and-prejudice",
    config: retrievalConfig({ retrieval_mode: "bm25", label: "+bm25" }),
    metrics: metrics({ accuracy: 0.69 * scale, spoiler_leakage_rate: 0, sample_size: 62 }),
  },
  {
    id: `${runId}-ret-3`, eval_run_id: runId, axis: "retrieval",
    label: "+ cross-encoder rerank", book_key: "pride-and-prejudice",
    config: retrievalConfig({ retrieval_mode: "rerank", label: "+rerank" }),
    metrics: metrics({ accuracy: 0.72 * scale, spoiler_leakage_rate: 0, sample_size: 62 }),
  },
  {
    id: `${runId}-ret-4`, eval_run_id: runId, axis: "retrieval",
    label: "Graph-constrained (roster + evidence first)", book_key: "pride-and-prejudice",
    config: retrievalConfig({ retrieval_mode: "graph_constrained", label: "graph-constrained" }),
    metrics: metrics({ accuracy: Math.min(0.88 * scale, 0.97), spoiler_leakage_rate: 0, sample_size: 62 }),
  },
];

/** Model-axis rows, extraction/retrieval held at their recommended configuration. */
const modelResults = (runId: string, scale: number): EvalResultOut[] => [
  {
    id: `${runId}-mod-1`, eval_run_id: runId, axis: "model",
    label: "Qwen3-8B-AWQ, local", book_key: "pride-and-prejudice",
    config: modelConfig({ model_mode: "local", label: "local" }),
    metrics: metrics({ accuracy: 0.79 * scale, ece: Math.max(0.14 / scale, 0.03), sample_size: 62 }),
  },
  {
    id: `${runId}-mod-2`, eval_run_id: runId, axis: "model",
    label: "Frontier API", book_key: "pride-and-prejudice",
    config: modelConfig({ model_mode: "frontier", label: "frontier" }),
    metrics: metrics({ accuracy: Math.min(0.9 * scale, 0.97), ece: Math.max(0.08 / scale, 0.02), sample_size: 62 }),
  },
  {
    id: `${runId}-mod-3`, eval_run_id: runId, axis: "model",
    label: "Routed (local, escalate on low confidence)", book_key: "pride-and-prejudice",
    config: modelConfig({ model_mode: "routed", label: "routed" }),
    metrics: metrics({ accuracy: Math.min(0.89 * scale, 0.96), ece: Math.max(0.05 / scale, 0.015), sample_size: 62 }),
  },
];

const buildRun = (id: string, createdAt: string, scale: number, notes: string): EvalRunOut => {
  const results = [
    ...extractionResults(id, scale),
    ...retrievalResults(id, scale),
    ...modelResults(id, scale),
  ];
  return {
    id,
    corpus_version: "pride-and-prejudice-v2",
    git_sha: id === "run-3" ? "a1b2c3d" : id === "run-2" ? "9f8e7d6" : "5c4b3a2",
    notes,
    created_at: createdAt,
    metrics: metrics({
      precision: 0.87 * scale,
      recall: 0.81 * scale,
      f1: 0.839 * scale,
      accuracy: Math.min(0.88 * scale, 0.96),
      ece: Math.max(0.06 / scale, 0.02),
      spoiler_leakage_rate: 0,
      sample_size: 62,
    }),
    results,
  };
};

export const EVAL_RUNS: EvalRunOut[] = [
  buildRun("run-1", "2026-09-08T09:00:00Z", 0.9, "First full-matrix pass — pre-calibration."),
  buildRun("run-2", "2026-09-18T09:00:00Z", 0.96, "Gold set expanded to 60 questions, two novels."),
  buildRun("run-3", "2026-09-27T09:00:00Z", 1.0, "Post-calibration; regression gate wired to this run."),
];

export const LATEST_RUN: EvalRunOut = EVAL_RUNS[EVAL_RUNS.length - 1] as EvalRunOut;

export const CALIBRATION: CalibrationModelOut = {
  task_type: "relation_confidence",
  version: 3,
  ece_before: 0.146,
  ece_after: 0.031,
  fitted_on_n: 1840,
  bins: [
    { confidence_lower: 0.0, confidence_upper: 0.2, predicted_confidence: 0.11, observed_accuracy: 0.09, sample_size: 42 },
    { confidence_lower: 0.2, confidence_upper: 0.4, predicted_confidence: 0.31, observed_accuracy: 0.27, sample_size: 88 },
    { confidence_lower: 0.4, confidence_upper: 0.6, predicted_confidence: 0.52, observed_accuracy: 0.49, sample_size: 214 },
    { confidence_lower: 0.6, confidence_upper: 0.8, predicted_confidence: 0.71, observed_accuracy: 0.69, sample_size: 512 },
    { confidence_lower: 0.8, confidence_upper: 0.95, predicted_confidence: 0.88, observed_accuracy: 0.86, sample_size: 640 },
    { confidence_lower: 0.95, confidence_upper: 1.0, predicted_confidence: 0.98, observed_accuracy: 0.95, sample_size: 344 },
  ],
};

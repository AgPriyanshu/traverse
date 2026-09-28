import type { AblationAxis, AblationConfig, EvalResultOut, MetricSet } from "./types";

export const AXIS_ORDER: AblationAxis[] = ["extraction", "retrieval", "model"];

export const AXIS_LABEL: Record<AblationAxis, string> = {
  extraction: "Extraction",
  retrieval: "Retrieval",
  model: "Model",
};

/**
 * PRD Appendix A names one recommended row per axis explicitly — two-pass
 * extraction with the full alias cascade, graph-constrained retrieval, a
 * routed model. There is no `is_recommended` field on the contract, so this
 * is read structurally off `AblationConfig` rather than off `label` text,
 * which stays free-form.
 */
export const isRecommended = (config: AblationConfig): boolean => {
  if (config.axis === "extraction") {
    return (
      config.extraction_mode === "two_pass" &&
      config.alias_mode === "full_cascade" &&
      !config.with_human_review
    );
  }
  if (config.axis === "retrieval") { return config.retrieval_mode === "graph_constrained"; }
  return config.model_mode === "routed";
};

/** The naive starting point each axis's progression is measured against (README's "run each axis against the recommended configuration of the others, plus the recommended row itself"). */
export const isBaseline = (config: AblationConfig): boolean => {
  if (config.axis === "extraction") {
    return (
      config.extraction_mode === "single_pass" &&
      config.alias_mode === "string_only" &&
      !config.with_human_review
    );
  }
  if (config.axis === "retrieval") { return config.retrieval_mode === "vector_only"; }
  return config.model_mode === "local";
};

const FLAG_LABEL: Record<string, string> = {
  single_pass: "single-pass",
  two_pass: "two-pass",
  string_only: "string-only",
  full_cascade: "full alias cascade",
  vector_only: "vector-only",
  bm25: "+BM25",
  rerank: "+rerank",
  graph_constrained: "graph-constrained",
  local: "local",
  frontier: "frontier",
  routed: "routed",
};

/** A short, plain-English summary of the flags that vary within one axis — never restates the axis name, since the table already groups by it. */
export const configSummary = (config: AblationConfig): string => {
  const parts: string[] = [];
  if (config.extraction_mode) { parts.push(FLAG_LABEL[config.extraction_mode] ?? config.extraction_mode); }
  if (config.alias_mode) { parts.push(FLAG_LABEL[config.alias_mode] ?? config.alias_mode); }
  if (config.with_human_review) { parts.push("+ human review"); }
  if (config.retrieval_mode) { parts.push(FLAG_LABEL[config.retrieval_mode] ?? config.retrieval_mode); }
  if (config.model_mode) { parts.push(FLAG_LABEL[config.model_mode] ?? config.model_mode); }
  return parts.join(", ");
};

export type MetricKey = keyof Omit<MetricSet, "sample_size">;

export const METRIC_LABEL: Record<MetricKey, string> = {
  precision: "Precision",
  recall: "Recall",
  f1: "F1",
  accuracy: "Accuracy",
  ece: "ECE",
  spoiler_leakage_rate: "Spoiler leakage",
};

/** ECE and spoiler-leakage are the only metrics where *lower* is the improvement — everything else climbs. */
const LOWER_IS_BETTER: ReadonlySet<MetricKey> = new Set(["ece", "spoiler_leakage_rate"]);

export type MetricDelta = { value: number; improved: boolean };

export const deltaFor = (metric: MetricKey, cell: MetricSet, baseline: MetricSet): MetricDelta | null => {
  const current = cell[metric];
  const base = baseline[metric];
  if (current === null || base === null) { return null; }
  const value = current - base;
  const improved = LOWER_IS_BETTER.has(metric) ? value < 0 : value > 0;
  return { value, improved };
};

export const groupByAxis = (results: readonly EvalResultOut[]): Map<AblationAxis, EvalResultOut[]> => {
  const groups = new Map<AblationAxis, EvalResultOut[]>();
  for (const axis of AXIS_ORDER) { groups.set(axis, []); }
  for (const result of results) {
    const bucket = groups.get(result.axis) ?? [];
    bucket.push(result);
    groups.set(result.axis, bucket);
  }
  return groups;
};

export const baselineFor = (results: readonly EvalResultOut[]): EvalResultOut | null => {
  return results.find((result) => isBaseline(result.config)) ?? null;
};

/** The two or three metrics each axis's table columns lead with — the rest are still in the full bundle behind "drill in." */
export const HEADLINE_METRICS: Record<AblationAxis, MetricKey[]> = {
  extraction: ["precision", "recall", "f1"],
  retrieval: ["accuracy", "spoiler_leakage_rate"],
  model: ["accuracy", "ece"],
};

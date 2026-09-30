export type AblationAxis = "extraction" | "retrieval" | "model";

export type AblationConfig = {
  axis: AblationAxis;
  label: string;
  extraction_mode: "single_pass" | "two_pass" | null;
  alias_mode: "string_only" | "full_cascade" | null;
  with_human_review: boolean;
  retrieval_mode: "vector_only" | "bm25" | "rerank" | "graph_constrained" | null;
  model_mode: "local" | "frontier" | "routed" | null;
};

export type MetricSet = {
  precision: number | null;
  recall: number | null;
  f1: number | null;
  accuracy: number | null;
  ece: number | null;
  spoiler_leakage_rate: number | null;
  sample_size: number;
};

export type EvalResultOut = {
  id: string;
  eval_run_id: string;
  axis: AblationAxis;
  label: string;
  book_key: string | null;
  config: AblationConfig;
  metrics: MetricSet;
};

export type EvalRunOut = {
  id: string;
  corpus_version: string | null;
  git_sha: string | null;
  metrics: MetricSet;
  notes: string | null;
  results: EvalResultOut[];
  created_at: string;
};

export type CalibrationBinOut = {
  confidence_lower: number;
  confidence_upper: number;
  predicted_confidence: number;
  observed_accuracy: number;
  sample_size: number;
};

export type CalibrationModelOut = {
  task_type: string;
  version: number;
  bins: CalibrationBinOut[];
  ece_before: number | null;
  ece_after: number | null;
  fitted_on_n: number;
};

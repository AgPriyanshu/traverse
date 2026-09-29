import type { AblationConfig, EvalResult, EvalRun, MetricSet, RoutingPolicy } from "@/lib/api";
import type { CostBreakdown, CostTrendPoint, LlmPurpose, ModelChoice } from "./types";
import { LLM_PURPOSES } from "./types";

/**
 * Illustrative unit economics — $ per call, by purpose and model choice.
 * There is no live per-call cost meter yet (that is `CostBreakdown`'s own
 * gap, see `./types.ts`), so these are labelled placeholders sized off the
 * real numbers in `plans/sprint-8/RETRO.md` (Qwen3-8B-AWQ local inference
 * amortizes to near-zero marginal cost per call; a frontier judge call in the
 * S8 ablation ran a few cents). `routed` is deliberately the average of the
 * other two, not a third independent number — it is what "fall back to
 * frontier only when local is unavailable" costs in expectation, not a
 * distinct model.
 */
export const PURPOSE_UNIT_COST_USD: Record<LlmPurpose, Record<ModelChoice, number>> = {
  chapter_classify: { local: 0.0004, frontier: 0.012, routed: 0.0062 },
  character_extract: { local: 0.0018, frontier: 0.041, routed: 0.0214 },
  relation_extract: { local: 0.0026, frontier: 0.058, routed: 0.0303 },
  adjudicate: { local: 0.0011, frontier: 0.026, routed: 0.0136 },
  answer: { local: 0.0009, frontier: 0.021, routed: 0.0110 },
  judge: { local: 0.0013, frontier: 0.034, routed: 0.0177 },
};

/** How often one answered question calls each purpose — `judge` only runs during eval, not on a live ask, so its query-time weight is 0. */
export const CALLS_PER_QUERY: Record<LlmPurpose, number> = {
  chapter_classify: 0,
  character_extract: 0,
  relation_extract: 0,
  adjudicate: 0,
  answer: 1,
  judge: 0,
};

export const costPerQueryFor = (policy: Record<LlmPurpose, ModelChoice>): number => {
  return LLM_PURPOSES.reduce((total, purpose) => {
    const calls = CALLS_PER_QUERY[purpose];
    if (calls === 0) { return total; }
    return total + calls * PURPOSE_UNIT_COST_USD[purpose][policy[purpose]];
  }, 0);
};

/** The policy this dashboard opens with until a live `GET /ops/routing-policy` (S9.6) replaces it. */
export const DEFAULT_POLICY: RoutingPolicy = {
  version: 0,
  purposes: {
    chapter_classify: "local",
    character_extract: "local",
    relation_extract: "local",
    adjudicate: "local",
    answer: "local",
    judge: "frontier",
  },
};

const day = (offset: number): string => {
  const base = new Date("2026-09-22T00:00:00Z");
  base.setUTCDate(base.getUTCDate() + offset);
  return base.toISOString();
};

/**
 * A week of rolling cost windows with two policy changes annotated — "that
 * last annotation is what makes the chart an argument rather than a
 * picture" (frontend-1.md). Fixture, matching `CostBreakdown`'s exact shape;
 * swap for real `cost_snapshot` rows the moment do1 exposes a windowed
 * listing route.
 */
export const COST_TREND: readonly CostTrendPoint[] = [
  { window_start: day(0), window_end: day(1), total_cost_usd: 4.82, by_stage: { chapter_classify: 0.61, character_extract: 1.94, relation_extract: 2.02, answer: 0.25 }, by_purpose: { chapter_classify: 0.61, character_extract: 1.94, relation_extract: 2.02, answer: 0.25 }, query_count: 278, book_count: 3, policy_change: null },
  { window_start: day(1), window_end: day(2), total_cost_usd: 5.10, by_stage: { chapter_classify: 0.64, character_extract: 2.03, relation_extract: 2.14, answer: 0.29 }, by_purpose: { chapter_classify: 0.64, character_extract: 2.03, relation_extract: 2.14, answer: 0.29 }, query_count: 301, book_count: 3, policy_change: null },
  { window_start: day(2), window_end: day(3), total_cost_usd: 4.97, by_stage: { chapter_classify: 0.60, character_extract: 1.98, relation_extract: 2.08, answer: 0.31 }, by_purpose: { chapter_classify: 0.60, character_extract: 1.98, relation_extract: 2.08, answer: 0.31 }, query_count: 296, book_count: 3, policy_change: null },
  { window_start: day(3), window_end: day(4), total_cost_usd: 11.38, by_stage: { chapter_classify: 0.62, character_extract: 2.01, relation_extract: 2.10, answer: 6.65 }, by_purpose: { chapter_classify: 0.62, character_extract: 2.01, relation_extract: 2.10, answer: 6.65 }, query_count: 312, book_count: 3, policy_change: "answer routed to frontier" },
  { window_start: day(4), window_end: day(5), total_cost_usd: 11.9, by_stage: { chapter_classify: 0.63, character_extract: 2.05, relation_extract: 2.12, answer: 7.10 }, by_purpose: { chapter_classify: 0.63, character_extract: 2.05, relation_extract: 2.12, answer: 7.10 }, query_count: 331, book_count: 3, policy_change: null },
  { window_start: day(5), window_end: day(6), total_cost_usd: 5.44, by_stage: { chapter_classify: 0.65, character_extract: 2.10, relation_extract: 2.18, answer: 0.51 }, by_purpose: { chapter_classify: 0.65, character_extract: 2.10, relation_extract: 2.18, answer: 0.51 }, query_count: 340, book_count: 3, policy_change: "answer reverted to local" },
  { window_start: day(6), window_end: day(7), total_cost_usd: 5.52, by_stage: { chapter_classify: 0.66, character_extract: 2.08, relation_extract: 2.21, answer: 0.57 }, by_purpose: { chapter_classify: 0.66, character_extract: 2.08, relation_extract: 2.21, answer: 0.57 }, query_count: 347, book_count: 3, policy_change: null },
];

export const LATEST_COST_WINDOW: CostBreakdown = COST_TREND[COST_TREND.length - 1] as CostBreakdown;

const metrics = (accuracy: number, sampleSize: number): MetricSet => ({
  precision: null,
  recall: null,
  f1: null,
  accuracy,
  ece: null,
  spoiler_leakage_rate: null,
  sample_size: sampleSize,
});

const modelConfig = (label: string, modelMode: AblationConfig["model_mode"]): AblationConfig => ({
  axis: "model",
  label,
  extraction_mode: null,
  alias_mode: null,
  with_human_review: false,
  retrieval_mode: null,
  model_mode: modelMode,
});

/**
 * Fallback accuracy-by-model-mode data for a dev environment with no
 * recorded ablation run (`GET /ops/eval-runs/latest` 404s until
 * `make eval-ablation` has run at least once against this worktree's own
 * database — every worktree's Postgres is isolated, BRANCH.md §4). Shaped
 * exactly like a real `EvalRunOut`'s `results` so this panel renders
 * identically whichever source wins; not used when a real run exists.
 */
export const FALLBACK_MODEL_AXIS_RESULTS: readonly EvalResult[] = [
  { id: "fixture-local", eval_run_id: "fixture-run", axis: "model", label: "Local (Qwen3-8B-AWQ)", book_key: null, config: modelConfig("Local (Qwen3-8B-AWQ)", "local"), metrics: metrics(0.79, 38) },
  { id: "fixture-routed", eval_run_id: "fixture-run", axis: "model", label: "Routed (local, frontier fallback)", book_key: null, config: modelConfig("Routed (local, frontier fallback)", "routed"), metrics: metrics(0.81, 38) },
  { id: "fixture-frontier", eval_run_id: "fixture-run", axis: "model", label: "Frontier API", book_key: null, config: modelConfig("Frontier API", "frontier"), metrics: metrics(0.84, 38) },
];

export const FALLBACK_EVAL_RUN: EvalRun = {
  id: "fixture-run",
  corpus_version: null,
  git_sha: null,
  metrics: metrics(0.79, 38),
  notes: "Fixture — no ablation run recorded in this worktree's database yet.",
  results: FALLBACK_MODEL_AXIS_RESULTS as EvalResult[],
  created_at: day(0),
};

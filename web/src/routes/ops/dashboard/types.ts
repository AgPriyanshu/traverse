import type { AblationConfig, MetricSet, RoutingPolicy } from "@/lib/api";

/**
 * Hand-mirrored from `api/contracts/api.py`'s `CostBreakdown` — no route
 * returns it yet (be2/do1 own the routing-policy engine and its cost
 * accounting, S9.6/S9.7, not landed in this worktree as of this commit), so
 * `openapi-typescript` has nothing to generate it from: FastAPI only emits a
 * schema for a type a route actually references. Same exception as
 * `routes/ops/evals/types.ts` at the Sprint 8 freeze — delete this type the
 * moment a real `/ops/cost-breakdown`-shaped route exists and switch to the
 * generated `Schemas["CostBreakdown"]`.
 */
export type CostBreakdown = {
  window_start: string;
  window_end: string;
  total_cost_usd: number;
  by_stage: Record<string, number>;
  by_purpose: Record<string, number>;
  query_count: number;
  book_count: number;
};

export const LLM_PURPOSES = [
  "chapter_classify",
  "character_extract",
  "relation_extract",
  "adjudicate",
  "answer",
  "judge",
] as const;

export type LlmPurpose = (typeof LLM_PURPOSES)[number];

/** The two purposes a query in flight can actually route through — the ones ETH-4/NFR-residency care about. */
export const QUERY_PURPOSES: readonly LlmPurpose[] = ["answer", "judge"];

export type ModelChoice = "local" | "frontier" | "routed";

export const MODEL_CHOICES: readonly ModelChoice[] = [
  "local",
  "frontier",
  "routed",
];

export type PurposePolicy = Record<LlmPurpose, ModelChoice>;

/**
 * A synthetic day-over-day cost trend annotated with policy changes
 * (`frontend-1.md`: "that last annotation is what makes the chart an
 * argument rather than a picture"). Each point mirrors `CostBreakdown`'s own
 * fields plus the one thing a trend needs that a single snapshot doesn't — a
 * label for what changed, if anything, right before this window closed.
 */
export type CostTrendPoint = CostBreakdown & {
  policy_change: string | null;
};

export type RoutingTradeoff = {
  policy: RoutingPolicy;
  costPerQuery: number;
  accuracy: number | null;
  sampleSize: number;
};

export const findModelAxisResult = (
  results: readonly { axis: string; config: AblationConfig; metrics: MetricSet }[],
  modelMode: ModelChoice,
) => {
  return results.find(
    (result) => result.axis === "model" && result.config.model_mode === modelMode,
  );
};

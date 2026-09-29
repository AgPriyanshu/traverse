import { useRoutingPolicy } from "@/lib/api";
import type { RoutingPolicy } from "@/lib/api";

/**
 * Mirrors `LLMPurpose` (`api/contracts/enums.py`) — every purpose the
 * routing policy can set a model choice for. Shared between the ops
 * dashboard's routing control (S9.10) and the inference-mode labelling below
 * (S9.11, ETH-4/NFR-residency) so both read one definition of "the current
 * policy," never two that can drift.
 */
export const LLM_PURPOSES = [
  "chapter_classify",
  "character_extract",
  "relation_extract",
  "adjudicate",
  "answer",
  "judge",
] as const;

export type LlmPurpose = (typeof LLM_PURPOSES)[number];

/** The purposes a live query in flight actually touches — what ETH-4/NFR-residency ask this file to label. */
export const QUERY_PURPOSES: readonly LlmPurpose[] = ["answer", "judge"];

/** The purposes an upload's extraction pipeline touches — what the upload consent step (S9.11) gates on. */
export const EXTRACTION_PURPOSES: readonly LlmPurpose[] = [
  "chapter_classify",
  "character_extract",
  "relation_extract",
  "adjudicate",
];

export type ModelChoice = "local" | "frontier" | "routed";

export const MODEL_CHOICES: readonly ModelChoice[] = ["local", "frontier", "routed"];

export type PurposePolicy = Record<LlmPurpose, ModelChoice>;

/** `frontier` and `routed` both mean this purpose's calls can leave the machine — `routed` falls back to frontier, it doesn't avoid it. */
export const isEgress = (choice: ModelChoice): boolean => choice !== "local";

/** The policy this app assumes until a live `GET /ops/routing-policy` (S9.6, be2) replaces it — fully local except the eval-only judge purpose. */
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

export const asPolicyRecord = (policy: RoutingPolicy): PurposePolicy => {
  const record = {} as PurposePolicy;
  for (const purpose of LLM_PURPOSES) {
    const value = (policy.purposes ?? {})[purpose];
    record[purpose] = value === "frontier" || value === "routed" ? value : "local";
  }
  return record;
};

export const modelChoiceFor = (policy: PurposePolicy, purposes: readonly LlmPurpose[]): ModelChoice => {
  if (purposes.some((purpose) => policy[purpose] === "frontier")) { return "frontier"; }
  if (purposes.some((purpose) => policy[purpose] === "routed")) { return "routed"; }
  return "local";
};

/**
 * The routing policy actually in effect right now, live when `GET
 * /ops/routing-policy` (S9.6) has landed, `DEFAULT_POLICY` while it is still
 * a `not_implemented` stub — the same graceful-degrade shape as the ops
 * dashboard's routing panel (`routes/ops/dashboard/routing-control-panel.tsx`),
 * because a query-in-flight label that shows "not built yet" instead of a
 * mode is worse than a labelled assumption (ETH-4 needs *a* visible answer,
 * not a blank one).
 */
export const useEffectivePolicy = (): { policy: PurposePolicy; isLive: boolean } => {
  const routingPolicy = useRoutingPolicy();
  if (routingPolicy.data) {
    return { policy: asPolicyRecord(routingPolicy.data), isLive: true };
  }
  return { policy: asPolicyRecord(DEFAULT_POLICY), isLive: false };
};

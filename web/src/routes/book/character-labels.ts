import type { ImportanceTier, ResolutionMethod } from "@/lib/api";

/** Display order for tier sections — protagonists lead, a phone book does not. */
export const TIER_ORDER: ImportanceTier[] = [
  "protagonist",
  "major",
  "minor",
  "mentioned",
];

export const TIER_LABEL: Record<ImportanceTier, string> = {
  protagonist: "Protagonists",
  major: "Major",
  minor: "Minor",
  mentioned: "Mentioned",
};

export const TIER_LABEL_SINGULAR: Record<ImportanceTier, string> = {
  protagonist: "Protagonist",
  major: "Major",
  minor: "Minor",
  mentioned: "Mentioned",
};

/**
 * "nickname table", not "NICKNAME" — the trust affordance only works if the
 * reason reads like an answer to "why?" (design brief, S3.12).
 */
export const RESOLUTION_METHOD_LABEL: Record<ResolutionMethod, string> = {
  exact: "exact match",
  normalised: "spelling normalised",
  honorific: "honorific stripped",
  nickname: "nickname table",
  embedding: "embedding similarity",
  llm: "model judgement",
  human: "human reviewed",
};

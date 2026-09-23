import type { RelationFamily } from "@/lib/api";

export const FAMILY_ORDER: RelationFamily[] = [
  "kinship",
  "romantic",
  "social",
  "adversarial",
  "structural",
];

export const FAMILY_LABEL: Record<RelationFamily, string> = {
  kinship: "Kinship",
  romantic: "Romantic",
  social: "Social",
  adversarial: "Adversarial",
  structural: "Structural",
};

export const FAMILY_LINE_NAME: Record<RelationFamily, string> = {
  kinship: "solid",
  romantic: "dashed",
  social: "dotted",
  adversarial: "dash-dot",
  structural: "long dash",
};

/** Empty means solid. Colour is never the only channel that separates families (design/DESIGN.md §2). */
export const FAMILY_DASH: Record<RelationFamily, number[]> = {
  kinship: [],
  romantic: [7, 5],
  social: [2, 4],
  adversarial: [9, 4, 2, 4],
  structural: [16, 3],
};

// The ontology has a structural family but DCR-5 has not yet added a colour token for it, so it borrows the muted ink.
export const FAMILY_COLOR_VAR: Record<RelationFamily, string> = {
  kinship: "var(--chakra-colors-relation-kinship)",
  romantic: "var(--chakra-colors-relation-romantic)",
  social: "var(--chakra-colors-relation-social)",
  adversarial: "var(--chakra-colors-relation-adversarial)",
  structural: "var(--chakra-colors-fg-muted)",
};

export const predicateLabel = (predicate: string): string => {
  return predicate.replace(/_/g, " ");
};

import { Badge } from "@chakra-ui/react";
import type { ImportanceTier } from "@/lib/api";
import { TIER_LABEL_SINGULAR } from "./character-labels";

export type CharacterTierBadgeProps = {
  tier: ImportanceTier;
};

/**
 * Protagonist gets the accent treatment; every other tier stays neutral —
 * there is no per-tier token, and inventing one here would be exactly the
 * "literal colour outside tokens.ts" AGENTS.md rules out.
 */
export const CharacterTierBadge = ({ tier }: CharacterTierBadgeProps) => {
  const isProtagonist = tier === "protagonist";

  return (
    <Badge
      textStyle="small"
      fontWeight="600"
      bg={isProtagonist ? "accent.subtle" : "bg.sunken"}
      color={isProtagonist ? "accent.fg" : "fg.muted"}
      borderWidth="1px"
      borderColor={isProtagonist ? "accent.solid" : "border"}
      borderRadius="md"
      paddingInline="2.5"
      paddingBlock="0.5"
    >
      {TIER_LABEL_SINGULAR[tier]}
    </Badge>
  );
};

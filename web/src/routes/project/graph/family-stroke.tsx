import { HStack, Text } from "@chakra-ui/react";
import type { RelationFamily } from "@/lib/api";
import {
  FAMILY_COLOR_VAR,
  FAMILY_DASH,
  FAMILY_LABEL,
  FAMILY_LINE_NAME,
} from "./relation-style";

export type FamilyStrokeProps = {
  family: RelationFamily;
  width?: number;
};

export const FamilyStroke = ({ family, width = 32 }: FamilyStrokeProps) => {
  return (
    <svg width={width} height={8} aria-hidden="true" focusable="false">
      <line
        x1={1}
        y1={4}
        x2={width - 1}
        y2={4}
        stroke={FAMILY_COLOR_VAR[family]}
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeDasharray={FAMILY_DASH[family].join(" ") || undefined}
      />
    </svg>
  );
};

export const FamilyBadge = ({ family }: { family: RelationFamily }) => {
  return (
    <HStack gap="1.5" as="span" display="inline-flex" title={`${FAMILY_LABEL[family]}, drawn ${FAMILY_LINE_NAME[family]}`}>
      <FamilyStroke family={family} width={24} />
      <Text as="span" textStyle="small" color="fg.muted">
        {FAMILY_LABEL[family]}
      </Text>
    </HStack>
  );
};

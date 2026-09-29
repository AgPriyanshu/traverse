import { Box, HStack, Stack, Text } from "@chakra-ui/react";
import { formatCurrency } from "@/lib/format";

export type CostSegment = {
  label: string;
  value: number;
};

export type StackedCostBarProps = {
  segments: readonly CostSegment[];
  total: number;
  /** Accessible name for the bar as a whole — the segments below are its table equivalent. */
  ariaLabel: string;
};

/**
 * One horizontal bar, cost by stage. A single hue at a graduated opacity
 * step per segment (dataviz: sequential magnitude, one hue light->dark)
 * rather than a distinct categorical colour per stage — stage names carry
 * identity through their text label directly on the bar and in the list
 * below, never through colour alone, so a 5th or 6th stage never needs a
 * hue nobody validated for contrast (`tokens.ts` is frozen; this stays
 * inside the accent ramp it already ships).
 */
export const StackedCostBar = ({ segments, total, ariaLabel }: StackedCostBarProps) => {
  const sorted = [...segments].sort((a, b) => b.value - a.value).filter((segment) => segment.value > 0);
  const OPACITY_FLOOR = 0.22;
  const OPACITY_CEIL = 0.9;
  const step = sorted.length > 1 ? (OPACITY_CEIL - OPACITY_FLOOR) / (sorted.length - 1) : 0;

  if (total <= 0 || sorted.length === 0) {
    return (
      <Text textStyle="body" color="fg.muted">
        No cost recorded in this window.
      </Text>
    );
  }

  return (
    <Stack gap="3">
      <HStack
        gap="0.5"
        h="8"
        borderRadius="md"
        overflow="hidden"
        role="img"
        aria-label={ariaLabel}
      >
        {sorted.map((segment, index) => (
          <Box
            key={segment.label}
            flex={`${segment.value} 0 0%`}
            h="full"
            bg="accent.solid"
            opacity={OPACITY_CEIL - index * step}
            minW="2px"
            title={`${segment.label}: ${formatCurrency(segment.value)}`}
          />
        ))}
      </HStack>

      <Stack gap="1.5" as="ul" role="list">
        {sorted.map((segment, index) => (
          <HStack key={segment.label} as="li" justify="space-between" gap="3">
            <HStack gap="2" minW="0">
              <Box
                boxSize="2.5"
                borderRadius="sm"
                bg="accent.solid"
                opacity={OPACITY_CEIL - index * step}
                flexShrink="0"
                aria-hidden="true"
              />
              <Text textStyle="small" color="fg" truncate>
                {segment.label}
              </Text>
            </HStack>
            <Text textStyle="data" color="fg.muted" flexShrink="0">
              {formatCurrency(segment.value)} · {((segment.value / total) * 100).toFixed(0)}%
            </Text>
          </HStack>
        ))}
      </Stack>
    </Stack>
  );
};

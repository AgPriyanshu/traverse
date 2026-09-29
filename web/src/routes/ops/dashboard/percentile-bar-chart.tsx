import { Box, HStack, Stack, Text } from "@chakra-ui/react";
import { formatDuration } from "@/lib/format";

export type PercentileSet = {
  p50: number | null;
  p95: number | null;
  p99: number | null;
  n: number;
};

export type PercentileBarChartProps = {
  stages: ReadonlyArray<{ label: string; percentiles: PercentileSet }>;
};

const SERIES: ReadonlyArray<{ key: keyof PercentileSet & string; label: string; opacity: number }> = [
  { key: "p50", label: "p50", opacity: 0.35 },
  { key: "p95", label: "p95", opacity: 0.65 },
  { key: "p99", label: "p99", opacity: 0.95 },
];

const MS_TO_PX = 0.12;
const MIN_BAR_PX = 3;

/**
 * p50/p95/p99 per stage as one hue at three opacity steps, not three
 * categorical colours — the three percentiles are an ordered progression
 * (how extreme the tail is), which is exactly what a sequential ramp
 * encodes, not an identity dataviz would ask for distinct hues on. p95 gets
 * a direct value label (the number the NFR-perf budget actually gates on);
 * p50/p99 surface on hover via the native title tooltip, so labels don't
 * crowd 3 bars × N stages.
 */
export const PercentileBarChart = ({ stages }: PercentileBarChartProps) => {
  if (stages.length === 0) {
    return (
      <Text textStyle="body" color="fg.muted">
        No query samples recorded yet.
      </Text>
    );
  }

  return (
    <Stack gap="4">
      <HStack gap="4" aria-hidden="true">
        {SERIES.map((series) => (
          <HStack key={series.key} gap="1.5">
            <Box boxSize="2.5" borderRadius="sm" bg="accent.solid" opacity={series.opacity} />
            <Text textStyle="small" color="fg.muted">{series.label}</Text>
          </HStack>
        ))}
      </HStack>

      <Stack gap="3" role="table" aria-label="Query latency by stage, p50/p95/p99">
        {stages.map((stage) => (
          <Stack key={stage.label} gap="1" role="row">
            <Text textStyle="small" fontWeight="600" color="fg">{stage.label}</Text>
            <HStack gap="1.5" align="flex-end" h="10">
              {SERIES.map((series) => {
                const value = stage.percentiles[series.key] ?? 0;
                return (
                  <Box key={series.key} h="full" display="flex" alignItems="flex-end">
                    <Box
                      w="7"
                      minH={`${MIN_BAR_PX}px`}
                      h={`${Math.max(value * MS_TO_PX, MIN_BAR_PX)}px`}
                      bg="accent.solid"
                      opacity={series.opacity}
                      borderRadius="sm"
                    >
                      <title>{`${stage.label} ${series.label}: ${formatDuration(value)} (n=${stage.percentiles.n})`}</title>
                    </Box>
                  </Box>
                );
              })}
              <Text textStyle="data" color="fg.muted" paddingBottom="0.5">
                p95 {formatDuration(stage.percentiles.p95)}
              </Text>
            </HStack>
          </Stack>
        ))}
      </Stack>
    </Stack>
  );
};

import { Box, SimpleGrid, Stack, Text } from "@chakra-ui/react";
import { formatAbsoluteTime, formatPercent } from "@/lib/format";
import type { EvalRunOut } from "./types";

export type MetricTrendChartProps = {
  runs: readonly EvalRunOut[];
};

const WIDTH = 280;
const HEIGHT = 120;
const PAD_X = 8;
const PAD_Y = 14;

type Series = {
  key: "f1" | "spoiler_leakage_rate";
  label: string;
  /** Lower is the win for leakage, higher for F1 — the axis title says which, never a colour convention the reader has to infer. */
  goodDirection: "up" | "down";
};

const SERIES: Series[] = [
  { key: "f1", label: "Overall F1", goodDirection: "up" },
  { key: "spoiler_leakage_rate", label: "Spoiler leakage rate", goodDirection: "down" },
];

/**
 * Two single-series mini line charts, never one chart with two y-scales
 * (dataviz skill's #1 anti-pattern) — F1 and spoiler-leakage live on
 * incomparable scales in practice (leakage should hug zero) and each gets
 * its own axis instead of being squeezed onto a shared one.
 */
export const MetricTrendChart = ({ runs }: MetricTrendChartProps) => {
  if (runs.length < 2) {
    return (
      <Text textStyle="body" color="fg.muted">
        Trend needs at least two runs — only {runs.length} recorded so far.
      </Text>
    );
  }

  return (
    <SimpleGrid columns={{ base: 1, md: 2 }} gap="5">
      {SERIES.map((series) => {
        const values = runs.map((run) => run.metrics[series.key] ?? 0);
        const min = Math.min(...values);
        const max = Math.max(...values);
        const span = Math.max(max - min, 0.001);
        const stepX = (WIDTH - PAD_X * 2) / (runs.length - 1);
        const toY = (value: number): number =>
          HEIGHT - PAD_Y - ((value - min) / span) * (HEIGHT - PAD_Y * 2);

        const points = values.map((value, index) => `${PAD_X + index * stepX},${toY(value)}`).join(" ");
        const first = values[0] as number;
        const last = values[values.length - 1] as number;
        const improved = series.goodDirection === "up" ? last >= first : last <= first;

        return (
          <Stack key={series.key} gap="1" borderWidth="1px" borderColor="border" borderRadius="lg" bg="bg.surface" padding="3">
            <Text textStyle="small" fontWeight="600" color="fg">{series.label}</Text>
            <Box>
              <svg width={WIDTH} height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${series.label} across ${runs.length} eval runs`}>
                <line x1={PAD_X} y1={HEIGHT - PAD_Y} x2={WIDTH - PAD_X} y2={HEIGHT - PAD_Y} stroke="var(--chakra-colors-border)" strokeWidth={1} />
                <polyline points={points} fill="none" stroke={improved ? "var(--chakra-colors-status-ok)" : "var(--chakra-colors-status-err)"} strokeWidth={2} />
                {values.map((value, index) => (
                  <circle
                    key={runs[index]?.id}
                    cx={PAD_X + index * stepX}
                    cy={toY(value)}
                    r={4}
                    fill={improved ? "var(--chakra-colors-status-ok)" : "var(--chakra-colors-status-err)"}
                  >
                    <title>{`${formatAbsoluteTime(runs[index]?.created_at)}: ${formatPercent(value)}`}</title>
                  </circle>
                ))}
              </svg>
            </Box>
            <Text textStyle="small" color={improved ? "status.ok" : "status.err"}>
              {formatPercent(first)} → {formatPercent(last)} over {runs.length} runs
            </Text>
          </Stack>
        );
      })}
    </SimpleGrid>
  );
};

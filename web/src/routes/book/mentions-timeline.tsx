import { Box, HStack, Text } from "@chakra-ui/react";
import { useMemo } from "react";
import { SparklineBars } from "./sparkline-bars";
import type { SparkPoint } from "./sparkline-bars";

export type MentionsTimelineProps = {
  histogram: Record<string, number>;
  selectedChapter: string | null;
  onSelectChapter: (chapter: string | null) => void;
};

const AXIS_TICK_COUNT = 5;

const toPoints = (histogram: Record<string, number>): SparkPoint[] => {
  const entries = Object.entries(histogram);
  entries.sort(([keyA], [keyB]) => {
    const numberA = Number(keyA);
    const numberB = Number(keyB);
    const isNumberA = Number.isFinite(numberA);
    const isNumberB = Number.isFinite(numberB);
    if (isNumberA && isNumberB) { return numberA - numberB; }
    if (isNumberA) { return -1; }
    if (isNumberB) { return 1; }
    return keyA.localeCompare(keyB);
  });
  return entries.map(([key, value]) => ({
    key,
    label: Number.isFinite(Number(key)) ? `Chapter ${key}` : "Unplaced mentions",
    value,
  }));
};

/**
 * Chapters on x, mention count on y, click a bar to filter the mention list
 * (S3.11). A single-series magnitude chart needs no legend or multi-hue
 * palette (dataviz skill) — one accent hue, scaled by value, is the whole
 * encoding, with the selected bar carrying a visible ring so colour is never
 * the only channel for which one is picked.
 */
export const MentionsTimeline = ({
  histogram,
  selectedChapter,
  onSelectChapter,
}: MentionsTimelineProps) => {
  // useMemos.
  const points = useMemo(() => toPoints(histogram), [histogram]);
  const axisTicks = useMemo(() => pickAxisTicks(points, AXIS_TICK_COUNT), [points]);

  if (points.length === 0) {
    return (
      <Text textStyle="body" color="fg.muted">
        No per-chapter mention data yet.
      </Text>
    );
  }

  return (
    <Box>
      <SparklineBars
        data={points}
        width={1000}
        height={92}
        responsive
        interactive
        selectedKey={selectedChapter}
        onSelect={onSelectChapter}
        ariaLabel="mentions per chapter"
      />
      {points.length > 1 ? (
        <HStack justify="space-between" marginBlockStart="1.5">
          {axisTicks.map((point) => (
            <Text key={point.key} textStyle="data" color="fg.subtle">
              {point.label}
            </Text>
          ))}
        </HStack>
      ) : null}
    </Box>
  );
};

/** A handful of evenly-spaced labels, not one per bar — 61 chapter labels under a 400px chart is unreadable, not thorough. */
const pickAxisTicks = (points: SparkPoint[], count: number): SparkPoint[] => {
  if (points.length <= count) { return points; }
  const step = (points.length - 1) / (count - 1);
  const indices = Array.from({ length: count }, (_unused, index) =>
    Math.round(index * step),
  );
  const unique = [...new Set(indices)];
  return unique.map((index) => points[index] as SparkPoint);
};

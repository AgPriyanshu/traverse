import { Box, HStack, SimpleGrid, Stack, Table, Text } from "@chakra-ui/react";
import { formatCount, formatPercent } from "@/lib/format";
import type { CalibrationBinOut } from "./types";

export type CalibrationChartProps = {
  bins: readonly CalibrationBinOut[];
  eceBefore: number | null;
  eceAfter: number | null;
};

const SIZE = 340;
const PAD = 36;
const PLOT = SIZE - PAD * 2;
const MIN_RADIUS = 5;
const MAX_RADIUS = 13;

const toX = (value: number): number => PAD + value * PLOT;
const toY = (value: number): number => PAD + (1 - value) * PLOT;

const TICKS = [0, 0.25, 0.5, 0.75, 1];

/**
 * A reliability diagram: predicted confidence vs. observed accuracy, one
 * accent-hued series (a single series needs no legend box — dataviz skill),
 * marker radius carrying each bin's sample size. The diagonal is a labelled
 * reference, not just a drawn line (S8.7 DoD) — a model sitting on it is
 * calibrated by definition, which is the one fact this chart exists to show.
 */
export const CalibrationChart = ({ bins, eceBefore, eceAfter }: CalibrationChartProps) => {
  const maxSample = Math.max(1, ...bins.map((bin) => bin.sample_size));
  const radiusFor = (sampleSize: number): number =>
    MIN_RADIUS + (MAX_RADIUS - MIN_RADIUS) * Math.sqrt(sampleSize / maxSample);

  const linePoints = bins
    .map((bin) => `${toX(bin.predicted_confidence)},${toY(bin.observed_accuracy)}`)
    .join(" ");

  return (
    <Stack gap="4">
      <SimpleGrid columns={{ base: 1, sm: 2 }} gap="3" maxW="24rem">
        <Stack gap="0" borderWidth="1px" borderColor="border" borderRadius="md" padding="3" bg="bg.sunken">
          <Text textStyle="small" color="fg.muted">ECE before calibration</Text>
          <Text textStyle="heading" color="fg">{eceBefore === null ? "—" : formatPercent(eceBefore)}</Text>
        </Stack>
        <Stack gap="0" borderWidth="1px" borderColor="status.ok" borderRadius="md" padding="3" bg="bg.sunken">
          <Text textStyle="small" color="fg.muted">ECE after calibration</Text>
          <Text textStyle="heading" color="status.ok">{eceAfter === null ? "—" : formatPercent(eceAfter)}</Text>
        </Stack>
      </SimpleGrid>

      <Box borderWidth="1px" borderColor="border" borderRadius="lg" bg="bg.surface" padding="3" overflowX="auto">
        <svg
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          role="img"
          aria-label="Reliability diagram: predicted confidence against observed accuracy, with the perfect-calibration diagonal"
        >
          {TICKS.map((tick) => (
            <g key={tick}>
              <line x1={toX(tick)} y1={PAD} x2={toX(tick)} y2={SIZE - PAD} stroke="var(--chakra-colors-border)" strokeWidth={1} opacity={0.5} />
              <line x1={PAD} y1={toY(tick)} x2={SIZE - PAD} y2={toY(tick)} stroke="var(--chakra-colors-border)" strokeWidth={1} opacity={0.5} />
              <text x={toX(tick)} y={SIZE - PAD + 16} fontSize={10} fill="var(--chakra-colors-fg-muted)" textAnchor="middle">
                {tick.toFixed(2)}
              </text>
              <text x={PAD - 8} y={toY(tick) + 3} fontSize={10} fill="var(--chakra-colors-fg-muted)" textAnchor="end">
                {tick.toFixed(2)}
              </text>
            </g>
          ))}

          <text x={SIZE / 2} y={SIZE - 4} fontSize={11} fill="var(--chakra-colors-fg-muted)" textAnchor="middle">
            Predicted confidence
          </text>
          <text x={12} y={SIZE / 2} fontSize={11} fill="var(--chakra-colors-fg-muted)" textAnchor="middle" transform={`rotate(-90 12 ${SIZE / 2})`}>
            Observed accuracy
          </text>

          <line
            x1={toX(0)} y1={toY(0)} x2={toX(1)} y2={toY(1)}
            stroke="var(--chakra-colors-fg-subtle)"
            strokeWidth={2}
            strokeDasharray="6 5"
          />
          <text
            x={toX(0.62)} y={toY(0.62) - 8}
            fontSize={11}
            fill="var(--chakra-colors-fg-muted)"
            textAnchor="middle"
            transform={`rotate(-45 ${toX(0.62)} ${toY(0.62) - 8})`}
          >
            Perfect calibration
          </text>

          <polyline points={linePoints} fill="none" stroke="var(--chakra-colors-accent-solid)" strokeWidth={2} />

          {bins.map((bin) => (
            <circle
              key={`${bin.confidence_lower}-${bin.confidence_upper}`}
              cx={toX(bin.predicted_confidence)}
              cy={toY(bin.observed_accuracy)}
              r={radiusFor(bin.sample_size)}
              fill="var(--chakra-colors-accent-solid)"
              stroke="var(--chakra-colors-bg-surface)"
              strokeWidth={2}
            >
              <title>
                {`Predicted ${formatPercent(bin.predicted_confidence)}, observed ${formatPercent(bin.observed_accuracy)} — ${formatCount(bin.sample_size, "extraction")}`}
              </title>
            </circle>
          ))}
        </svg>
        <Text textStyle="small" color="fg.subtle" marginBlockStart="1">
          Marker size is the number of extractions in that confidence bin — hover a point for the exact numbers.
        </Text>
      </Box>

      <Table.Root size="sm" variant="line" aria-label="Calibration bins as a table — the chart's accessible equivalent">
        <Table.Header>
          <Table.Row>
            <Table.ColumnHeader>Confidence bin</Table.ColumnHeader>
            <Table.ColumnHeader textAlign="end">Predicted</Table.ColumnHeader>
            <Table.ColumnHeader textAlign="end">Observed</Table.ColumnHeader>
            <Table.ColumnHeader textAlign="end">Sample</Table.ColumnHeader>
          </Table.Row>
        </Table.Header>
        <Table.Body>
          {bins.map((bin) => (
            <Table.Row key={`${bin.confidence_lower}-${bin.confidence_upper}`}>
              <Table.Cell>
                <HStack gap="1">
                  <Text textStyle="data">{formatPercent(bin.confidence_lower, 0)}</Text>
                  <Text textStyle="data" color="fg.subtle">–</Text>
                  <Text textStyle="data">{formatPercent(bin.confidence_upper, 0)}</Text>
                </HStack>
              </Table.Cell>
              <Table.Cell textAlign="end">{formatPercent(bin.predicted_confidence)}</Table.Cell>
              <Table.Cell textAlign="end">{formatPercent(bin.observed_accuracy)}</Table.Cell>
              <Table.Cell textAlign="end">{bin.sample_size.toLocaleString()}</Table.Cell>
            </Table.Row>
          ))}
        </Table.Body>
      </Table.Root>
    </Stack>
  );
};

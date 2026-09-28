import { Badge, Box, Button, HStack, Heading, Stack, Table, Text } from "@chakra-ui/react";
import { formatPercent } from "@/lib/format";
import {
  AXIS_LABEL,
  AXIS_ORDER,
  HEADLINE_METRICS,
  baselineFor,
  configSummary,
  deltaFor,
  groupByAxis,
  isRecommended,
} from "./ablation-config";
import type { MetricKey } from "./ablation-config";
import type { EvalResultOut } from "./types";

export type AblationTableProps = {
  results: readonly EvalResultOut[];
  onDrillIn: (result: EvalResultOut) => void;
};

const MetricDelta = ({ metric, cell, baseline }: { metric: MetricKey; cell: EvalResultOut; baseline: EvalResultOut | null }) => {
  const value = cell.metrics[metric];
  if (value === null) {
    return <Text textStyle="data" color="fg.subtle">n/a</Text>;
  }
  const delta = baseline && baseline.id !== cell.id ? deltaFor(metric, cell.metrics, baseline.metrics) : null;
  return (
    <Stack gap="0">
      <Text textStyle="data" color="fg">{formatPercent(value)}</Text>
      {delta ? (
        <Text
          textStyle="small"
          color={delta.improved ? "status.ok" : "status.err"}
          aria-label={`${delta.improved ? "improved" : "regressed"} by ${formatPercent(Math.abs(delta.value))} versus baseline`}
        >
          {delta.value > 0 ? "▲" : delta.value < 0 ? "▼" : "–"} {formatPercent(Math.abs(delta.value))} vs. baseline
        </Text>
      ) : null}
    </Stack>
  );
};

/**
 * One sub-table per axis (PRD Appendix A) — grouping by axis rather than one
 * flat matrix keeps "what varied" legible, since every row already holds the
 * other two axes at their recommended configuration (README's "never the
 * full cross product").
 */
export const AblationTable = ({ results, onDrillIn }: AblationTableProps) => {
  const grouped = groupByAxis(results);

  return (
    <Stack gap="8">
      {AXIS_ORDER.map((axis) => {
        const rows = grouped.get(axis) ?? [];
        if (rows.length === 0) { return null; }
        const baseline = baselineFor(rows);
        const headline = HEADLINE_METRICS[axis];

        return (
          <Stack as="section" gap="3" key={axis}>
            <Heading as="h3" textStyle="subheading">
              {AXIS_LABEL[axis]}
            </Heading>

            <Box borderWidth="1px" borderColor="border" borderRadius="lg" bg="bg.surface" overflowX="auto">
              <Table.Root size="sm" variant="line">
                <Table.Header>
                  <Table.Row>
                    <Table.ColumnHeader>Configuration</Table.ColumnHeader>
                    {headline.map((metric) => (
                      <Table.ColumnHeader key={metric} textAlign="end">
                        {metric === "spoiler_leakage_rate" ? "Spoiler leakage" : metric === "ece" ? "ECE" : metric[0]?.toUpperCase() + metric.slice(1)}
                      </Table.ColumnHeader>
                    ))}
                    <Table.ColumnHeader />
                  </Table.Row>
                </Table.Header>
                <Table.Body>
                  {rows.map((result) => {
                    const recommended = isRecommended(result.config);
                    return (
                      <Table.Row
                        key={result.id}
                        bg={recommended ? "accent.subtle" : undefined}
                      >
                        <Table.Cell>
                          <Stack gap="0.5">
                            <HStack gap="2">
                              <Text textStyle="body" fontWeight={recommended ? "700" : "400"} color="fg">
                                {result.label}
                              </Text>
                              {recommended ? (
                                <Badge colorPalette="orange" size="sm">Recommended</Badge>
                              ) : null}
                              {result.id === baseline?.id ? (
                                <Badge variant="outline" size="sm">Baseline</Badge>
                              ) : null}
                            </HStack>
                            <Text textStyle="small" color="fg.muted">
                              {configSummary(result.config)}
                            </Text>
                          </Stack>
                        </Table.Cell>
                        {headline.map((metric) => (
                          <Table.Cell key={metric} textAlign="end">
                            <MetricDelta metric={metric} cell={result} baseline={baseline} />
                          </Table.Cell>
                        ))}
                        <Table.Cell textAlign="end">
                          <Button
                            size="xs"
                            variant="outline"
                            onClick={() => { onDrillIn(result); }}
                          >
                            Full metrics
                          </Button>
                        </Table.Cell>
                      </Table.Row>
                    );
                  })}
                </Table.Body>
              </Table.Root>
            </Box>
          </Stack>
        );
      })}
    </Stack>
  );
};

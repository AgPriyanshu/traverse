import { Box, Drawer, Portal, SimpleGrid, Stack, Text } from "@chakra-ui/react";
import { formatCount, formatPercent } from "@/lib/format";
import { AXIS_LABEL, configSummary, METRIC_LABEL } from "./ablation-config";
import type { MetricKey } from "./ablation-config";
import type { EvalResultOut } from "./types";

export type MetricDrawerProps = {
  result: EvalResultOut | null;
  onClose: () => void;
};

const METRIC_ORDER: MetricKey[] = ["precision", "recall", "f1", "accuracy", "ece", "spoiler_leakage_rate"];

/**
 * The full `MetricSet` for one ablation-matrix cell — the table row only ever
 * shows the two or three headline numbers that apply to its axis; this is
 * "drill into one cell's full metric bundle" (frontend-1.md, S8.7). The
 * contract has no per-question breakdown yet (`EvalResultOut` is one
 * aggregate per cell, not a list) — see `plans/sprint-8/HANDOFF.md`.
 */
export const MetricDrawer = ({ result, onClose }: MetricDrawerProps) => {
  return (
    <Drawer.Root
      open={result !== null}
      placement="end"
      onOpenChange={(details) => {
        if (!details.open) { onClose(); }
      }}
    >
      <Portal>
        <Drawer.Backdrop />
        <Drawer.Positioner>
          <Drawer.Content bg="bg.surface" maxW={{ base: "full", sm: "md" }}>
            {result ? (
              <>
                <Drawer.Header borderBottomWidth="1px" borderColor="border">
                  <Drawer.Title textStyle="subheading" color="fg">
                    {result.label}
                  </Drawer.Title>
                  <Text textStyle="data" color="fg.subtle">
                    {AXIS_LABEL[result.axis]} axis · {configSummary(result.config)}
                  </Text>
                </Drawer.Header>

                <Drawer.Body>
                  <Stack gap="5">
                    {result.book_key ? (
                      <Text textStyle="small" color="fg.muted">
                        Measured on <Text as="span" fontWeight="600">{result.book_key}</Text>, over{" "}
                        {formatCount(result.metrics.sample_size, "sample")}.
                      </Text>
                    ) : null}

                    <SimpleGrid columns={2} gap="4" role="table" aria-label="Full metric bundle for this cell">
                      {METRIC_ORDER.map((metric) => {
                        const value = result.metrics[metric];
                        return (
                          <Stack key={metric} gap="0" role="row" borderWidth="1px" borderColor="border" borderRadius="md" padding="3" bg="bg.sunken">
                            <Text role="rowheader" textStyle="small" color="fg.muted">
                              {METRIC_LABEL[metric]}
                            </Text>
                            <Text role="cell" textStyle="heading" color={value === null ? "fg.subtle" : "fg"}>
                              {value === null ? "n/a for this axis" : formatPercent(value)}
                            </Text>
                          </Stack>
                        );
                      })}
                    </SimpleGrid>

                    <Box borderTopWidth="1px" borderColor="border" paddingBlockStart="4">
                      <Text textStyle="small" color="fg.muted">
                        A blank metric is a field that does not apply to this axis (`MetricSet`'s fields
                        are all optional except sample size) — never a zero standing in for "not measured."
                      </Text>
                    </Box>
                  </Stack>
                </Drawer.Body>
              </>
            ) : null}
          </Drawer.Content>
        </Drawer.Positioner>
      </Portal>
    </Drawer.Root>
  );
};

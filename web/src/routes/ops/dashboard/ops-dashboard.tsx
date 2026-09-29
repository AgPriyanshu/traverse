import { Heading, Stack, Text } from "@chakra-ui/react";
import { CostPanel } from "./cost-panel";
import { HealthPanel } from "./health-panel";
import { PerformancePanel } from "./performance-panel";
import { RoutingControlPanel } from "./routing-control-panel";

/**
 * F7.1–7.4 — the ops dashboard: cost, performance, pipeline health, and the
 * routing control, in that reading order because the routing control is the
 * conclusion the first three panels' numbers build toward, not a fifth,
 * unrelated setting (S9.10, `plans/sprint-9/frontend-1.md`: "the demo's
 * closing argument").
 */
export const OpsDashboard = () => {
  return (
    <Stack gap="8">
      <Stack gap="2">
        <Heading as="h2" textStyle="heading">Operations</Heading>
        <Text textStyle="body" color="fg.muted" maxW="measure">
          What this deployment costs, how fast it answers, whether the
          pipeline is healthy — and the one lever that moves all three:
          which model serves each purpose.
        </Text>
      </Stack>

      <CostPanel />
      <PerformancePanel />
      <HealthPanel />
      <RoutingControlPanel />
    </Stack>
  );
};

export default OpsDashboard;

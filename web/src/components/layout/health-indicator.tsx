import { HStack } from "@chakra-ui/react";
import { useHealth } from "@/lib/api";
import { StatusDot } from "@/components/ui";
import type { StatusTone } from "@/components/ui";

/**
 * `GET /api/health` is the one endpoint that answers before its handler is
 * written, which makes it the honest signal for whether the API is reachable
 * at all this sprint.
 */
export const HealthIndicator = () => {
  // Apis.
  const health = useHealth();

  // Variables.
  const degraded = health.data?.dependencies?.filter((d) => !d.ok) ?? [];

  let tone: StatusTone = "idle";
  let label = "Checking";

  if (health.isError) {
    tone = "err";
    label = "API unreachable";
  } else if (health.data?.status === "ok") {
    tone = "ok";
    label = "All systems ready";
  } else if (health.data?.status === "degraded") {
    tone = "warn";
    label =
      degraded.length > 0
        ? `Degraded — ${degraded.map((d) => d.name).join(", ")}`
        : "Degraded";
  }

  return (
    <HStack gap="0" paddingInline="2" title={label}>
      <StatusDot tone={tone} label={label} labelHidden />
    </HStack>
  );
};

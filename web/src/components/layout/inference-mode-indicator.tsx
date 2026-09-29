import { HStack } from "@chakra-ui/react";
import { StatusDot } from "@/components/ui";
import { isEgress, useEffectivePolicy } from "@/lib/inference-mode";

/**
 * PRD ETH-4 / NFR-residency: "zero-egress must be visibly verifiable."
 * Persistent, app-wide, next to `<HealthIndicator>` — a query answered on
 * this machine or sent to a frontier API is not a settings-page fact, it is
 * a fact about what just happened to the reader's book, so it stays visible
 * everywhere a query could be asked, not only on the ask screen itself.
 *
 * Reads the `answer` purpose specifically — that is the purpose a live ask
 * actually calls (`QUERY_PURPOSES`, `@/lib/inference-mode`); `judge` never
 * runs on a live query, only during eval.
 */
export const InferenceModeIndicator = () => {
  const { policy, isLive } = useEffectivePolicy();
  const egress = isEgress(policy.answer);

  const label = egress
    ? policy.answer === "routed"
      ? "Routed — may leave this machine"
      : "Frontier API — leaves this machine"
    : "Fully local — nothing leaves this machine";

  return (
    <HStack
      gap="1.5"
      paddingInline="2"
      title={isLive ? label : `${label} (preview policy — live routing not wired up yet, S9.6)`}
    >
      <StatusDot tone={egress ? "warn" : "ok"} label={label} />
    </HStack>
  );
};

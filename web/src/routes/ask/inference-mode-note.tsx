import { HStack } from "@chakra-ui/react";
import { StatusDot } from "@/components/ui";
import { isEgress, useEffectivePolicy } from "@/lib/inference-mode";

/**
 * ETH-4 / NFR-residency, at the point of use rather than only the app-wide
 * `<InferenceModeIndicator>` in the top bar — the moment before a reader
 * submits a question is the moment "does this leave my machine" actually
 * matters, so this repeats the same fact right above the composer.
 */
export const InferenceModeNote = () => {
  const { policy, isLive } = useEffectivePolicy();
  const egress = isEgress(policy.answer);

  const label = egress
    ? "This question may be answered by a frontier API — its text leaves this machine."
    : "This question is answered fully on this machine.";

  return (
    <HStack gap="2" wrap="wrap">
      <StatusDot
        tone={egress ? "warn" : "ok"}
        label={isLive ? label : `${label} (preview policy — live routing not wired up yet, S9.6)`}
      />
    </HStack>
  );
};

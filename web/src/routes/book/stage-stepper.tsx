import { Box, Circle, HStack, Stack, Text } from "@chakra-ui/react";
import { StatusDot, toneForStageState } from "@/components/ui";
import type { StageName, StageStatus } from "@/lib/api";
import { STAGE_LABELS, STAGE_ORDER } from "@/lib/api";
import { formatDuration } from "@/lib/format";

export type StageStepperProps = {
  stages: StageStatus[] | undefined;
};

const MARKER_COLOR: Record<string, string> = {
  pending: "border.control",
  running: "accent.solid",
  succeeded: "status.ok",
  failed: "status.err",
  skipped: "border.control",
};

/**
 * Every frozen stage, always, in pipeline order — a stage the backend has not
 * reported yet shows as pending rather than disappearing. PRD F1.1: a
 * twenty-minute job with no visible progress reads as broken.
 */
export const StageStepper = ({ stages }: StageStepperProps) => {
  // Variables.
  const reported = new Map<StageName, StageStatus>(
    (stages ?? []).map((stage) => [stage.stage, stage]),
  );

  return (
    <Stack as="ol" gap="0" listStyleType="none" paddingInline="0">
      {STAGE_ORDER.map((name, index) => {
        const stage = reported.get(name);
        const state = stage?.state ?? "pending";
        const tone = toneForStageState(state);
        const isLast = index === STAGE_ORDER.length - 1;

        return (
          <HStack key={name} as="li" gap="4" align="stretch">
            <Stack gap="0" align="center" width="4" flexShrink="0">
              <Circle
                size="2.5"
                bg={state === "pending" ? "bg" : MARKER_COLOR[state]}
                borderWidth="1px"
                borderColor={MARKER_COLOR[state]}
                marginBlockStart="1.5"
                aria-hidden="true"
              />
              {!isLast ? (
                <Box
                  flex="1"
                  width="1px"
                  bg="border"
                  minHeight="6"
                  aria-hidden="true"
                />
              ) : null}
            </Stack>

            <Stack gap="1" paddingBlockEnd={isLast ? "0" : "5"} minWidth="0" flex="1">
              <Text
                textStyle="body"
                color={state === "pending" ? "fg.muted" : "fg"}
                fontWeight={state === "running" ? "500" : "400"}
              >
                {STAGE_LABELS[name]}
              </Text>

              <HStack gap="4" wrap="wrap">
                <StatusDot tone={tone.tone} label={tone.label} />
                {stage?.duration_ms !== undefined &&
                stage?.duration_ms !== null ? (
                  <Text textStyle="data" color="fg.subtle">
                    {formatDuration(stage.duration_ms)}
                  </Text>
                ) : null}
                {stage?.attempt !== undefined && stage.attempt > 1 ? (
                  <Text textStyle="data" color="fg.subtle">
                    attempt {stage.attempt}
                  </Text>
                ) : null}
              </HStack>

              {stage?.error ? (
                <Text textStyle="small" color="status.err" maxW="measure">
                  {stage.error}
                </Text>
              ) : null}
            </Stack>
          </HStack>
        );
      })}
    </Stack>
  );
};

import { Box, Button, HStack, Stack, Text } from "@chakra-ui/react";
import { useMemo, useState } from "react";
import type { ReviewTask } from "@/lib/api";
import { bulkDecisionFor } from "./bulk-decisions";
import { TASK_TYPE_LABEL, taskConfidence } from "./task-meta";
import type { Decision } from "./types";

const CONFIRM_THRESHOLD = 5;

export type BulkAcceptBarProps = {
  selectedTasks: readonly ReviewTask[];
  onAccept: (tasks: readonly ReviewTask[], decisionFor: (task: ReviewTask) => Decision, summaryLabel: string) => void;
  onClear: () => void;
};

/** S7.10: a group accept, never a blind one — the confidence range is always shown, and a large batch needs a second click. */
export const BulkAcceptBar = ({ selectedTasks, onAccept, onClear }: BulkAcceptBarProps) => {
  // States.
  const [confirming, setConfirming] = useState(false);

  // useMemos.
  const eligible = useMemo(
    () => selectedTasks.filter((task) => bulkDecisionFor(task) !== null),
    [selectedTasks],
  );
  const ineligibleCount = selectedTasks.length - eligible.length;
  const confidences = useMemo(
    () => eligible.map((task) => taskConfidence(task)).filter((value): value is number => value !== null),
    [eligible],
  );
  const typeLabel = useMemo(() => {
    const types = new Set(eligible.map((task) => task.task_type));
    return types.size === 1 ? TASK_TYPE_LABEL[[...types][0] as ReviewTask["task_type"]] : "mixed types";
  }, [eligible]);

  if (selectedTasks.length === 0) { return null; }

  // Handlers.
  const commit = () => {
    onAccept(
      eligible,
      (task) => bulkDecisionFor(task) as Decision,
      `Accepted ${eligible.length} ${typeLabel.toLowerCase()} task${eligible.length === 1 ? "" : "s"}`,
    );
    setConfirming(false);
  };

  const handleAcceptClick = () => {
    if (eligible.length > CONFIRM_THRESHOLD && !confirming) {
      setConfirming(true);
      return;
    }
    commit();
  };

  return (
    <Box
      position="sticky"
      bottom="0"
      borderWidth="1px"
      borderColor="accent.solid"
      bg="bg.surface"
      borderRadius="lg"
      boxShadow="raised"
      padding="4"
      role="region"
      aria-label="Bulk accept"
    >
      <Stack gap="2.5">
        <HStack justify="space-between" wrap="wrap" gap="2">
          <Text textStyle="body" color="fg" fontWeight="600">
            {selectedTasks.length} selected — {eligible.length} can be bulk-accepted ({typeLabel})
          </Text>
          <Button size="xs" variant="ghost" color="fg.muted" onClick={onClear}>
            Clear selection
          </Button>
        </HStack>

        {ineligibleCount > 0 ? (
          <Text textStyle="small" color="status.warn">
            {ineligibleCount} of the selected tasks need a per-task decision and will stay in the queue.
          </Text>
        ) : null}

        {confidences.length > 0 ? (
          <Text textStyle="data" color="fg.subtle">
            Confidence {Math.round(Math.min(...confidences) * 100)}%–{Math.round(Math.max(...confidences) * 100)}%
          </Text>
        ) : null}

        <HStack gap="3">
          <Button
            size="sm"
            variant="solid"
            bg={confirming ? "status.warn" : "accent.solid"}
            color="accent.contrast"
            borderRadius="md"
            disabled={eligible.length === 0}
            onClick={handleAcceptClick}
          >
            {confirming ? `Confirm — accept ${eligible.length} anyway` : `Accept ${eligible.length}`}
          </Button>
          {confirming ? (
            <Button size="sm" variant="ghost" color="fg.muted" onClick={() => { setConfirming(false); }}>
              Cancel
            </Button>
          ) : null}
        </HStack>
      </Stack>
    </Box>
  );
};

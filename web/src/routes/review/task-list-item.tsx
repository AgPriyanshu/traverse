import { Box, Button, HStack, Stack, Text } from "@chakra-ui/react";
import type { ReviewTask } from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";
import { TASK_TYPE_LABEL, formatTaskConfidence } from "./task-meta";

export type TaskListItemProps = {
  task: ReviewTask;
  isActive: boolean;
  isSelected: boolean;
  onSelect: () => void;
  onToggleSelected: () => void;
  summary: string;
};

export const TaskListItem = ({
  task,
  isActive,
  isSelected,
  onSelect,
  onToggleSelected,
  summary,
}: TaskListItemProps) => {
  // Variables.
  const confidence = formatTaskConfidence(task);

  return (
    <Box
      as="li"
      borderWidth="1px"
      borderColor={isActive ? "accent.solid" : "border"}
      bg={isActive ? "accent.subtle" : "bg.surface"}
      borderRadius="md"
      overflow="hidden"
    >
      <HStack gap="0" alignItems="stretch">
        <Button
          size="xs"
          variant="ghost"
          aria-pressed={isSelected}
          aria-label={isSelected ? "Remove from bulk selection" : "Select for bulk accept"}
          borderRadius="0"
          alignSelf="stretch"
          paddingInline="2.5"
          color={isSelected ? "accent.fg" : "fg.subtle"}
          onClick={onToggleSelected}
        >
          {isSelected ? "✓" : "○"}
        </Button>
        <Button
          variant="ghost"
          flex="1"
          justifyContent="flex-start"
          borderRadius="0"
          paddingInline="2.5"
          paddingBlock="2.5"
          height="auto"
          whiteSpace="normal"
          textAlign="left"
          onClick={onSelect}
          aria-current={isActive ? "true" : undefined}
        >
          <Stack gap="1" alignItems="flex-start" width="full">
            <Text textStyle="small" color="fg.subtle">{TASK_TYPE_LABEL[task.task_type]}</Text>
            <Text textStyle="body" color="fg" fontWeight="500" truncate width="full">
              {summary}
            </Text>
            <HStack gap="2" textStyle="data" color="fg.subtle">
              <Text as="span">priority {task.priority}</Text>
              {confidence ? <Text as="span">· {confidence}</Text> : null}
              <Text as="span">· {formatRelativeTime(task.created_at)}</Text>
            </HStack>
          </Stack>
        </Button>
      </HStack>
    </Box>
  );
};

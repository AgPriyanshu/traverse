import { HStack, Stack, Text, chakra } from "@chakra-ui/react";
import { EmptyState } from "@/components/ui";
import type { ReviewTask } from "@/lib/api";
import { taskSummary } from "./task-meta";
import { TaskListItem } from "./task-list-item";
import type { SortMode } from "./types";
import { SORT_LABEL, SORT_MODES } from "./types";

const Select = chakra("select");

export type TaskListProps = {
  tasks: readonly ReviewTask[];
  activeTaskId: string | undefined;
  selectedIds: ReadonlySet<string>;
  sortMode: SortMode;
  onSortModeChange: (mode: SortMode) => void;
  onSelectTask: (taskId: string) => void;
  onToggleSelected: (taskId: string) => void;
};

export const TaskList = ({
  tasks,
  activeTaskId,
  selectedIds,
  sortMode,
  onSortModeChange,
  onSelectTask,
  onToggleSelected,
}: TaskListProps) => {
  return (
    <Stack gap="3" minW={{ base: "full", lg: "22rem" }} maxW={{ lg: "22rem" }}>
      <HStack justify="space-between" wrap="wrap" gap="2">
        <Text textStyle="subheading" color="fg">
          {tasks.length} open
        </Text>
        <HStack gap="2">
          <Text asChild textStyle="small" color="fg.muted">
            <label htmlFor="review-sort">Sort</label>
          </Text>
          <Select
            id="review-sort"
            value={sortMode}
            onChange={(event) => { onSortModeChange(event.target.value as SortMode); }}
            borderWidth="1px"
            borderColor="border.control"
            borderRadius="md"
            bg="bg.surface"
            paddingInline="2"
            paddingBlock="1"
            textStyle="small"
            color="fg"
          >
            {SORT_MODES.map((mode) => (
              <option key={mode} value={mode}>{SORT_LABEL[mode]}</option>
            ))}
          </Select>
        </HStack>
      </HStack>

      {tasks.length === 0 ? (
        <EmptyState title="Queue clear" description="Nothing waiting on a human right now." />
      ) : (
        <Stack as="ul" gap="1.5" maxH={{ lg: "calc(100vh - 16rem)" }} overflowY={{ lg: "auto" }}>
          {tasks.map((task) => (
            <TaskListItem
              key={task.id}
              task={task}
              isActive={task.id === activeTaskId}
              isSelected={selectedIds.has(task.id)}
              onSelect={() => { onSelectTask(task.id); }}
              onToggleSelected={() => { onToggleSelected(task.id); }}
              summary={taskSummary(task)}
            />
          ))}
        </Stack>
      )}
    </Stack>
  );
};

import { Flex, HStack, Kbd, Stack, Text } from "@chakra-ui/react";
import { useRef, useState } from "react";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui";
import { BulkAcceptBar } from "./bulk-accept-bar";
import { ShortcutsOverlay } from "./shortcuts-overlay";
import { TaskDetail } from "./task-detail";
import { TaskList } from "./task-list";
import { useReviewQueue } from "./use-review-queue";
import { useReviewShortcuts } from "./use-review-shortcuts";
import type { TaskShortcutMap } from "./types";

export type ReviewQueueProps = {
  projectId: string;
  heading: string;
};

/**
 * Split view: task list left, active task right, never a modal — a modal per
 * task costs an open/close cycle 50 times (S7.8). Everything a reviewer needs
 * happens without the mouse; buttons exist too, but the keys are the point.
 */
export const ReviewQueue = ({ projectId, heading }: ReviewQueueProps) => {
  // States.
  const [legendOpen, setLegendOpen] = useState(false);

  // Refs.
  const taskHandlersRef = useRef<TaskShortcutMap>({});

  // Apis.
  const queue = useReviewQueue(projectId);

  // Variables.
  const selectedTasks = queue.tasks.filter((task) => queue.selectedIds.has(task.id));
  if (!queue.activeTask) {
    // No renderer is mounted to keep this current, so a task no longer on
    // screen can't leave a stale decision key bound to it.
    taskHandlersRef.current = {};
  }

  // Hooks.
  useReviewShortcuts(
    {
      onNext: queue.goNext,
      onPrev: queue.goPrev,
      onToggleSelect: () => { if (queue.activeTask) { queue.toggleSelected(queue.activeTask.id); } },
      onUndo: queue.undoLast,
      onToggleLegend: () => { setLegendOpen((open) => !open); },
    },
    taskHandlersRef,
    !legendOpen,
  );

  // Early returns.
  if (queue.tasksQuery.isPending) {
    return <LoadingSkeleton variant="rows" count={6} label="Loading the review queue" />;
  }
  if (queue.tasksQuery.error) {
    return <ErrorState error={queue.tasksQuery.error} onRetry={() => void queue.tasksQuery.refetch()} />;
  }

  return (
    <Stack gap="4">
      <Stack gap="1">
        <Text textStyle="heading" color="fg">{heading}</Text>
        <HStack gap="1" wrap="wrap" textStyle="small" color="fg.muted">
          <Text as="span">Move with</Text>
          <Kbd>j</Kbd><Text as="span">/</Text><Kbd>k</Kbd>
          <Text as="span">, decide with</Text>
          <Kbd>a</Kbd><Text as="span">/</Text><Kbd>e</Kbd><Text as="span">/</Text><Kbd>m</Kbd><Text as="span">/</Text><Kbd>s</Kbd><Text as="span">/</Text><Kbd>r</Kbd>
          <Text as="span">, undo with</Text>
          <Kbd>u</Kbd>
          <Text as="span">, full list with</Text>
          <Kbd>?</Kbd>
        </HStack>
      </Stack>

      {queue.total === 0 ? (
        <EmptyState
          title="Queue clear"
          description="Nothing is waiting on a human decision for this project right now."
        />
      ) : (
        <Flex direction={{ base: "column", lg: "row" }} gap="5" alignItems="flex-start">
          <TaskList
            tasks={queue.tasks}
            activeTaskId={queue.activeTask?.id}
            selectedIds={queue.selectedIds}
            sortMode={queue.sortMode}
            onSortModeChange={queue.setSortMode}
            onSelectTask={queue.setActiveTaskId}
            onToggleSelected={queue.toggleSelected}
          />

          <Stack flex="1" minW="0" gap="4" width="full">
            {queue.activeTask ? (
              <TaskDetail
                task={queue.activeTask}
                position={queue.activeIndex + 1}
                total={queue.total}
                onResolve={(decision) => { if (queue.activeTask) { queue.resolveOne(queue.activeTask, decision); } }}
                onNext={queue.goNext}
                onPrev={queue.goPrev}
                taskHandlersRef={taskHandlersRef}
              />
            ) : null}

            <BulkAcceptBar
              selectedTasks={selectedTasks}
              onAccept={queue.resolveMany}
              onClear={queue.clearSelection}
            />
          </Stack>
        </Flex>
      )}

      <ShortcutsOverlay open={legendOpen} onClose={() => { setLegendOpen(false); }} />
    </Stack>
  );
};

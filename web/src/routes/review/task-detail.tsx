import { Box, Button, HStack, Stack, Text } from "@chakra-ui/react";
import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import type { ReviewTask } from "@/lib/api";
import { TaskShortcutsRefContext } from "./shortcuts-context";
import { TASK_TYPE_LABEL, taskSummary } from "./task-meta";
import type { Decision, TaskShortcutMap } from "./types";
import { ClassifyCandidateRenderer } from "./renderers/classify-candidate-renderer";
import { ConfirmChapterSplitRenderer } from "./renderers/confirm-chapter-split-renderer";
import { ConfirmRelationRenderer } from "./renderers/confirm-relation-renderer";
import { MergeRenderer } from "./renderers/merge-renderer";
import { ResolveConflictRenderer } from "./renderers/resolve-conflict-renderer";

export type TaskDetailProps = {
  task: ReviewTask;
  position: number;
  total: number;
  onResolve: (decision: Decision) => void;
  onNext: () => void;
  onPrev: () => void;
  taskHandlersRef: RefObject<TaskShortcutMap>;
};

/**
 * Renders whichever of the five task types is active. This is the one place
 * that switches on `task.payload.task_type` — each branch hands the renderer
 * its already-narrowed payload, so no renderer imports the union itself.
 */
export const TaskDetail = ({ task, position, total, onResolve, onNext, onPrev, taskHandlersRef }: TaskDetailProps) => {
  // Refs.
  const headingRef = useRef<HTMLHeadingElement>(null);

  const { payload } = task;

  // useEffects.
  useEffect(() => {
    // Advancing with j/k must never drop focus into the document body — the
    // heading is the one stable anchor across every renderer, so a screen
    // reader announces the new task the same way it would a page navigation.
    headingRef.current?.focus();
  }, [task.id]);

  return (
    <Stack gap="4" flex="1" minW="0">
      <HStack justify="space-between" wrap="wrap" gap="2">
        <Stack gap="0.5">
          <Text textStyle="small" color="fg.subtle">
            Task {position} of {total} · {TASK_TYPE_LABEL[task.task_type]}
          </Text>
          <Text ref={headingRef} as="h2" textStyle="heading" color="fg" tabIndex={-1} outline="none">
            {taskSummary(task)}
          </Text>
        </Stack>
        <HStack gap="2">
          <Button size="xs" variant="outline" borderColor="border.control" color="fg" borderRadius="md" onClick={onPrev} disabled={position <= 1}>
            ← Prev (k)
          </Button>
          <Button size="xs" variant="outline" borderColor="border.control" color="fg" borderRadius="md" onClick={onNext} disabled={position >= total}>
            Next (j) →
          </Button>
        </HStack>
      </HStack>

      <Box borderWidth="1px" borderColor="border" borderRadius="lg" bg="bg.surface" padding="5">
        <TaskShortcutsRefContext.Provider value={taskHandlersRef}>
          {payload.task_type === "merge_characters" || payload.task_type === "merge_across_books" ? (
            <MergeRenderer payload={payload} onResolve={onResolve} />
          ) : null}
          {payload.task_type === "confirm_relation" ? (
            <ConfirmRelationRenderer payload={payload} onResolve={onResolve} />
          ) : null}
          {payload.task_type === "resolve_conflict" ? (
            <ResolveConflictRenderer payload={payload} onResolve={onResolve} />
          ) : null}
          {payload.task_type === "classify_candidate" ? (
            <ClassifyCandidateRenderer payload={payload} onResolve={onResolve} />
          ) : null}
          {payload.task_type === "confirm_chapter_split" ? (
            <ConfirmChapterSplitRenderer payload={payload} onResolve={onResolve} />
          ) : null}
        </TaskShortcutsRefContext.Provider>
      </Box>
    </Stack>
  );
};

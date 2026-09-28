import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { toaster } from "@/components/ui";
import {
  pageRenderQueryOptions,
  useResolveReviewTask,
  useReviewTasks,
} from "@/lib/api";
import type { ReviewTask } from "@/lib/api";
import { compareTasks, firstCitation } from "./task-meta";
import type { Decision, SortMode } from "./types";
import { SORT_MODES } from "./types";

/**
 * Long enough that a reviewer moving at speed can catch a mis-key without
 * slowing down to avoid one, short enough it never feels like a queue.
 */
const UNDO_GRACE_MS = 5000;
const PREFETCH_AHEAD = 3;

type PendingResolution = {
  taskIds: string[];
  timeoutId: ReturnType<typeof setTimeout>;
  toastId: string;
};

/**
 * Whatever will occupy the resolved task's slot next — never just "the first
 * remaining task", which would yank a reviewer back to the top of the queue
 * every time they resolve anything but the current top item.
 */
const nextVisible = (sorted: readonly ReviewTask[], removedIds: readonly string[]): ReviewTask | null => {
  const anchor = sorted.findIndex((task) => removedIds.includes(task.id));
  if (anchor === -1) { return null; }
  for (let i = anchor + 1; i < sorted.length; i += 1) {
    if (!removedIds.includes(sorted[i]?.id ?? "")) { return sorted[i] ?? null; }
  }
  for (let i = anchor - 1; i >= 0; i -= 1) {
    if (!removedIds.includes(sorted[i]?.id ?? "")) { return sorted[i] ?? null; }
  }
  return null;
};

export const useReviewQueue = (projectId: string | undefined) => {
  // States.
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(new Set());

  // Refs.
  const pendingRef = useRef<Map<string, PendingResolution>>(new Map());
  const pendingOrderRef = useRef<string[]>([]);
  const decisionsByTaskId = useRef<Map<string, Decision>>(new Map());

  // Hooks.
  const [searchParams, setSearchParams] = useSearchParams();

  // Apis.
  const queryClient = useQueryClient();
  const tasksQuery = useReviewTasks(
    projectId ? { project_id: projectId, status: "open", limit: 200 } : undefined,
  );
  const resolveTask = useResolveReviewTask();

  // Variables.
  const sortMode = (searchParams.get("sort") as SortMode | null) ?? "priority";
  const activeTaskId = searchParams.get("task");

  // useMemos.
  const sorted = useMemo(() => {
    const open = (tasksQuery.data ?? []).filter((task) => !hiddenIds.has(task.id));
    return [...open].sort(compareTasks(SORT_MODES.includes(sortMode) ? sortMode : "priority"));
  }, [tasksQuery.data, hiddenIds, sortMode]);

  const activeIndex = useMemo(() => {
    if (!activeTaskId) { return 0; }
    const index = sorted.findIndex((task) => task.id === activeTaskId);
    return index === -1 ? 0 : index;
  }, [sorted, activeTaskId]);

  const activeTask: ReviewTask | null = sorted[activeIndex] ?? null;

  // Handlers.
  const setActiveTaskId = useCallback(
    (taskId: string | null) => {
      setSearchParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          if (taskId) { next.set("task", taskId); } else { next.delete("task"); }
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const setSortMode = useCallback(
    (mode: SortMode) => {
      setSearchParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          next.set("sort", mode);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const goNext = useCallback(() => {
    const next = sorted[activeIndex + 1];
    if (next) { setActiveTaskId(next.id); }
  }, [sorted, activeIndex, setActiveTaskId]);

  const goPrev = useCallback(() => {
    const prev = sorted[activeIndex - 1];
    if (prev) { setActiveTaskId(prev.id); }
  }, [sorted, activeIndex, setActiveTaskId]);

  const toggleSelected = useCallback((taskId: string) => {
    setSelectedIds((previous) => {
      const next = new Set(previous);
      if (next.has(taskId)) { next.delete(taskId); } else { next.add(taskId); }
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => { setSelectedIds(new Set()); }, []);

  const commit = useCallback(
    (key: string) => {
      const pending = pendingRef.current.get(key);
      if (!pending) { return; }
      pendingRef.current.delete(key);
      pendingOrderRef.current = pendingOrderRef.current.filter((entry) => entry !== key);
      for (const taskId of pending.taskIds) {
        const resolution = decisionsByTaskId.current.get(taskId);
        decisionsByTaskId.current.delete(taskId);
        if (!resolution) { continue; }
        resolveTask.mutate(
          { taskId, resolution: { decision: resolution.decision, payload: resolution.payload } },
          {
            onError: () => {
              setHiddenIds((previous) => {
                const next = new Set(previous);
                next.delete(taskId);
                return next;
              });
              toaster.create({
                type: "error",
                title: "Could not save that decision",
                description: "It's back in the queue — try again.",
              });
            },
          },
        );
      }
    },
    [resolveTask],
  );

  const undo = useCallback((key: string) => {
    const pending = pendingRef.current.get(key);
    if (!pending) { return false; }
    clearTimeout(pending.timeoutId);
    pendingRef.current.delete(key);
    pendingOrderRef.current = pendingOrderRef.current.filter((entry) => entry !== key);
    toaster.dismiss(pending.toastId);
    setHiddenIds((previous) => {
      const next = new Set(previous);
      for (const taskId of pending.taskIds) {
        next.delete(taskId);
        decisionsByTaskId.current.delete(taskId);
      }
      return next;
    });
    return true;
  }, []);

  const undoLast = useCallback(() => {
    const key = pendingOrderRef.current.at(-1);
    if (!key) {
      toaster.create({ type: "info", title: "Nothing to undo" });
      return;
    }
    undo(key);
  }, [undo]);

  const resolveOne = useCallback(
    (task: ReviewTask, decision: Decision) => {
      const key = task.id;
      decisionsByTaskId.current.set(task.id, decision);
      setHiddenIds((previous) => new Set(previous).add(task.id));
      setSelectedIds((previous) => {
        if (!previous.has(task.id)) { return previous; }
        const next = new Set(previous);
        next.delete(task.id);
        return next;
      });

      if (task.id === activeTask?.id) {
        setActiveTaskId(nextVisible(sorted, [task.id])?.id ?? null);
      }

      const toastId = toaster.create({
        type: "info",
        title: decision.label,
        duration: UNDO_GRACE_MS,
        action: { label: "Undo", onClick: () => { undo(key); } },
      });
      const timeoutId = setTimeout(() => { commit(key); }, UNDO_GRACE_MS);
      pendingRef.current.set(key, { taskIds: [task.id], timeoutId, toastId });
      pendingOrderRef.current.push(key);
    },
    [activeTask, sorted, setActiveTaskId, undo, commit],
  );

  const resolveMany = useCallback(
    (tasks: readonly ReviewTask[], decisionFor: (task: ReviewTask) => Decision, summaryLabel: string) => {
      if (tasks.length === 0) { return; }
      const key = `bulk:${tasks.map((task) => task.id).join(",")}`;
      const taskIds = tasks.map((task) => task.id);
      for (const task of tasks) { decisionsByTaskId.current.set(task.id, decisionFor(task)); }
      setHiddenIds((previous) => {
        const next = new Set(previous);
        for (const id of taskIds) { next.add(id); }
        return next;
      });
      setSelectedIds((previous) => {
        const next = new Set(previous);
        for (const id of taskIds) { next.delete(id); }
        return next;
      });

      if (taskIds.includes(activeTask?.id ?? "")) {
        setActiveTaskId(nextVisible(sorted, taskIds)?.id ?? null);
      }

      const toastId = toaster.create({
        type: "info",
        title: summaryLabel,
        duration: UNDO_GRACE_MS,
        action: { label: "Undo", onClick: () => { undo(key); } },
      });
      const timeoutId = setTimeout(() => { commit(key); }, UNDO_GRACE_MS);
      pendingRef.current.set(key, { taskIds, timeoutId, toastId });
      pendingOrderRef.current.push(key);
    },
    [activeTask, sorted, setActiveTaskId, undo, commit],
  );

  // useEffects.
  useEffect(() => {
    const pending = pendingRef.current;
    return () => {
      for (const entry of pending.values()) { clearTimeout(entry.timeoutId); }
    };
  }, []);

  useEffect(() => {
    const upcoming = sorted.slice(activeIndex + 1, activeIndex + 1 + PREFETCH_AHEAD);
    for (const task of upcoming) {
      const citation = firstCitation(task);
      if (!citation) { continue; }
      void queryClient.prefetchQuery(pageRenderQueryOptions(citation.bookId, citation.page));
    }
  }, [sorted, activeIndex, queryClient]);

  return {
    tasksQuery,
    tasks: sorted,
    activeTask,
    activeIndex,
    total: sorted.length,
    sortMode,
    setSortMode,
    setActiveTaskId,
    goNext,
    goPrev,
    selectedIds,
    toggleSelected,
    clearSelection,
    resolveOne,
    resolveMany,
    undoLast,
  };
};

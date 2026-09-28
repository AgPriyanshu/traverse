import type { ReviewTask } from "@/lib/api";

export type SortMode = "priority" | "confidence" | "age" | "importance";

export const SORT_MODES: readonly SortMode[] = ["priority", "confidence", "age", "importance"];

export const SORT_LABEL: Record<SortMode, string> = {
  priority: "Priority",
  confidence: "Confidence",
  age: "Age",
  importance: "Character importance",
};

/**
 * The generic shape `POST /review/tasks/{id}/resolve` takes (`ReviewResolution`
 * in the contract). `decision` strings are not part of the frozen contract —
 * be2 owns the resolution handlers, so this exact vocabulary is documented in
 * `plans/sprint-7/HANDOFF.md` for them to implement against.
 */
export type Decision = {
  decision: string;
  payload: Record<string, unknown>;
  /** Toast copy — chosen by the renderer that knows what it just did. */
  label: string;
};

export type ResolveFn = (task: ReviewTask, decision: Decision) => void;

/** A renderer's own key handlers, active only while its task is on screen. */
export type TaskShortcutMap = Record<string, () => void>;

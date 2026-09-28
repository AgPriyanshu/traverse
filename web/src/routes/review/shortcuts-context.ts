import { createContext, useContext } from "react";
import type { RefObject } from "react";
import type { TaskShortcutMap } from "./types";

export const TaskShortcutsRefContext = createContext<RefObject<TaskShortcutMap> | null>(null);

/**
 * Writes straight into the shared ref during render — no effect, no state,
 * so a keystroke inside one renderer's own inputs (e.g. the predicate select)
 * never triggers a re-render anywhere else. `useReviewShortcuts` reads the
 * same ref on every keydown, so it is always current by the next commit.
 */
export const useTaskShortcuts = (handlers: TaskShortcutMap): void => {
  const ref = useContext(TaskShortcutsRefContext);
  if (ref) { ref.current = handlers; }
};

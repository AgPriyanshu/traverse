import { useEffect } from "react";
import type { RefObject } from "react";
import type { TaskShortcutMap } from "./types";

export type GlobalShortcuts = {
  onNext: () => void;
  onPrev: () => void;
  onToggleSelect: () => void;
  onUndo: () => void;
  onToggleLegend: () => void;
};

const isTypingTarget = (target: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement)) { return false; }
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
};

/**
 * One document-level listener for the whole queue. `taskHandlers` comes from
 * whichever renderer is on screen (`useTaskShortcuts`) so the same key means
 * something different per task type without this hook knowing about payloads.
 */
export const useReviewShortcuts = (
  global: GlobalShortcuts,
  taskHandlersRef: RefObject<TaskShortcutMap>,
  enabled: boolean,
) => {
  useEffect(() => {
    if (!enabled) { return undefined; }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) { return; }
      if (isTypingTarget(event.target)) { return; }

      const key = event.key;
      switch (key) {
        case "j":
          event.preventDefault();
          global.onNext();
          return;
        case "k":
          event.preventDefault();
          global.onPrev();
          return;
        case "x":
          event.preventDefault();
          global.onToggleSelect();
          return;
        case "u":
          event.preventDefault();
          global.onUndo();
          return;
        case "?":
          event.preventDefault();
          global.onToggleLegend();
          return;
        default:
          break;
      }

      const handler = taskHandlersRef.current[key];
      if (handler) {
        event.preventDefault();
        handler();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => { document.removeEventListener("keydown", handleKeyDown); };
  }, [global, taskHandlersRef, enabled]);
};

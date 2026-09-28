import { useMemo, useState } from "react";
import type { Book } from "./api";
import {
  buildPositionSteps,
  indexForPosition,
  loadReadingPosition,
  positionForIndex,
  positionLabel,
  saveReadingPosition,
} from "./reading-position";
import type { SeriesPosition } from "./reading-position";

export type ReadingPositionState = {
  position: SeriesPosition | null;
  steps: ReturnType<typeof buildPositionSteps>;
  index: number;
  maxIndex: number;
  isLimited: boolean;
  label: string;
  setIndex: (index: number) => void;
};

/**
 * One reading position per project, persisted in `localStorage` — a reader's
 * position is per-viewer, never shared state (frontend-1.md, S8.6). Reloading
 * this hook under a different `projectId` (the same mounted layout, a new
 * route param) re-reads storage during render rather than in an effect, per
 * this codebase's own "resetting state when a prop changes" pattern
 * (`chunk-inspector.tsx`, `page-viewer.tsx`).
 */
export const useReadingPosition = (projectId: string, books: readonly Book[]): ReadingPositionState => {
  const steps = useMemo(() => buildPositionSteps(books), [books]);
  const [trackedProjectId, setTrackedProjectId] = useState(projectId);
  const [position, setPositionState] = useState<SeriesPosition | null>(() => loadReadingPosition(projectId));

  if (projectId !== trackedProjectId) {
    setTrackedProjectId(projectId);
    setPositionState(loadReadingPosition(projectId));
  }

  const index = indexForPosition(position, steps);

  const setIndex = (nextIndex: number) => {
    const next = positionForIndex(nextIndex, steps);
    setPositionState(next);
    saveReadingPosition(projectId, next);
  };

  return {
    position,
    steps,
    index,
    maxIndex: steps.length,
    isLimited: position !== null,
    label: positionLabel(position, steps),
    setIndex,
  };
};

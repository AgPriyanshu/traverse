import type { Relation } from "@/lib/api";

export type ArcSegment = {
  state: Relation;
  start: number;
  end: number;
  openEnded: boolean;
};

/**
 * A single-state arc is the one-element case of the same path: one segment, one
 * marker, no branch. Segments are clamped to run from their own first chapter to
 * the next state's first chapter, so a stale `last_chapter` cannot overlap.
 */
export const buildSegments = (
  states: readonly Relation[],
  chapterCount: number,
): ArcSegment[] => {
  const ordered = [...states].sort(
    (a, b) =>
      a.first_book_order - b.first_book_order ||
      (a.first_chapter ?? 1) - (b.first_chapter ?? 1),
  );
  return ordered.map((state, index) => {
    const start = state.first_chapter ?? 1;
    const next = ordered[index + 1];
    const declaredEnd = state.last_chapter ?? null;
    const openEnded = declaredEnd === null;
    let end = declaredEnd ?? chapterCount;
    if (next) {
      end = Math.min(end, Math.max(start, (next.first_chapter ?? start) - 1));
    }
    return { state, start, end: Math.max(start, end), openEnded };
  });
};

import type { Book } from "./api";

/**
 * The reader's position in a series: "I've read up to book N, chapter M."
 * `null` means fully caught up — no spoiler limit at all — and, like
 * `limit_book_order`/`limit_chapter` on the wire (query-path.md), that has to
 * be an explicit state, never something a missing value defaults into.
 */
export type SeriesPosition = { bookOrder: number; chapter: number };

const storageKey = (projectId: string): string => `traverse:reading-position:${projectId}`;

/** `localStorage` throws in private windows — this is a per-viewer convenience, never load-bearing. */
export const loadReadingPosition = (projectId: string): SeriesPosition | null => {
  try {
    const raw = window.localStorage.getItem(storageKey(projectId));
    if (!raw) { return null; }
    const parsed = JSON.parse(raw) as Partial<SeriesPosition>;
    if (typeof parsed.bookOrder !== "number" || typeof parsed.chapter !== "number") { return null; }
    return { bookOrder: parsed.bookOrder, chapter: parsed.chapter };
  } catch {
    return null;
  }
};

export const saveReadingPosition = (projectId: string, position: SeriesPosition | null): void => {
  try {
    if (position === null) {
      window.localStorage.removeItem(storageKey(projectId));
      return;
    }
    window.localStorage.setItem(storageKey(projectId), JSON.stringify(position));
  } catch {
    // Position just won't survive a reload; nothing else depends on the write succeeding.
  }
};

export type PositionStep = { bookOrder: number; chapter: number; bookTitle: string };

const orderOf = (book: Book): number => book.series_order ?? 1;

export const sortedByOrder = (books: readonly Book[]): Book[] =>
  [...books].sort((a, b) => orderOf(a) - orderOf(b));

/**
 * One slider step per chapter, every book's chapters laid end to end in
 * series order — the same "one axis across volumes" idea `arc-segments.ts`
 * uses for the relationship arc. A book with no chapters detected yet still
 * contributes one step so it isn't silently absent from the slider.
 */
export const buildPositionSteps = (books: readonly Book[]): PositionStep[] => {
  const steps: PositionStep[] = [];
  for (const book of sortedByOrder(books)) {
    const count = Math.max(book.chapter_count ?? 0, 1);
    for (let chapter = 1; chapter <= count; chapter += 1) {
      steps.push({ bookOrder: orderOf(book), chapter, bookTitle: book.title });
    }
  }
  return steps;
};

/** `steps.length` (one past the last real step) stands for "caught up" — a `null` position. */
export const indexForPosition = (position: SeriesPosition | null, steps: readonly PositionStep[]): number => {
  if (position === null) { return steps.length; }
  const exact = steps.findIndex((step) => step.bookOrder === position.bookOrder && step.chapter === position.chapter);
  if (exact !== -1) { return exact; }
  // Stale storage (a book's chapter count changed since the position was saved) clamps
  // to that book's last known step rather than throwing the position away entirely.
  let lastInBook = -1;
  steps.forEach((step, index) => {
    if (step.bookOrder === position.bookOrder) { lastInBook = index; }
  });
  return lastInBook === -1 ? steps.length : lastInBook;
};

export const positionForIndex = (index: number, steps: readonly PositionStep[]): SeriesPosition | null => {
  const step = steps[index];
  return step ? { bookOrder: step.bookOrder, chapter: step.chapter } : null;
};

export const positionLabel = (position: SeriesPosition | null, steps: readonly PositionStep[]): string => {
  if (position === null) { return "Caught up — no spoiler limit"; }
  const step = steps.find((s) => s.bookOrder === position.bookOrder && s.chapter === position.chapter);
  return step
    ? `Up to chapter ${position.chapter} of ${step.bookTitle}`
    : `Up to book ${position.bookOrder}, chapter ${position.chapter}`;
};

/**
 * The server params one specific book's screens (a book-scoped ask) should
 * send for a series-wide position. A book strictly after the reader's
 * position is entirely hidden (`limitChapter: 0` — before chapter 1, so
 * nothing in it clears the graph/retrieval/generation gate); a book at or
 * before it is capped at the position's own chapter, or left uncapped if the
 * reader has moved past it.
 */
export const limitsForBook = (
  position: SeriesPosition | null,
  bookOrder: number,
): { limitBookOrder: number; limitChapter: number | null } => {
  if (position === null || position.bookOrder > bookOrder) {
    return { limitBookOrder: bookOrder, limitChapter: null };
  }
  if (position.bookOrder < bookOrder) {
    return { limitBookOrder: bookOrder, limitChapter: 0 };
  }
  return { limitBookOrder: bookOrder, limitChapter: position.chapter };
};

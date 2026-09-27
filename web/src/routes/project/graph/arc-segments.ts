import type { Book, Relation } from "@/lib/api";
import { sortedBooks } from "../project-lookup";

export type ArcSegment = {
  state: Relation;
  startGlobal: number;
  endGlobal: number;
  openEnded: boolean;
};

export type BookBoundary = {
  book: Book;
  startGlobal: number;
  endGlobal: number;
};

const chapterCountOf = (book: Book): number => Math.max(1, book.chapter_count ?? 1);

/**
 * Lays every book's chapters end to end on one axis, in series order. A
 * standalone project is the one-book case of the same layout — one boundary,
 * spanning the whole axis — so the arc has a single code path whether it
 * spans one book or several (S5.12).
 */
export const buildBoundaries = (books: readonly Book[]): BookBoundary[] => {
  const ordered = sortedBooks(books);
  let cursor = 1;
  return ordered.map((book) => {
    const count = chapterCountOf(book);
    const startGlobal = cursor;
    const endGlobal = cursor + count - 1;
    cursor = endGlobal + 1;
    return { book, startGlobal, endGlobal };
  });
};

export const totalGlobalChapters = (boundaries: readonly BookBoundary[]): number => {
  const last = boundaries[boundaries.length - 1];
  return last ? last.endGlobal : 1;
};

const globalChapter = (
  boundaries: readonly BookBoundary[],
  bookOrder: number,
  chapter: number | null,
): number => {
  const boundary =
    boundaries.find((entry) => entry.book.series_order === bookOrder) ??
    boundaries[boundaries.length - 1];
  if (!boundary) { return 1; }
  const withinBook = Math.max(1, chapter ?? 1);
  return boundary.startGlobal + withinBook - 1;
};

/**
 * A single-state arc is the one-element case of the same path: one segment,
 * one marker, no branch. Segments are clamped to run from their own first
 * position to the next state's first position, so a stale `last_chapter`
 * cannot overlap — now compared on the whole-series axis, not one book's.
 */
export const buildSegments = (
  states: readonly Relation[],
  boundaries: readonly BookBoundary[],
): ArcSegment[] => {
  const total = totalGlobalChapters(boundaries);
  const ordered = [...states].sort(
    (a, b) =>
      a.first_book_order - b.first_book_order ||
      (a.first_chapter ?? 1) - (b.first_chapter ?? 1),
  );
  return ordered.map((state, index) => {
    const startGlobal = globalChapter(boundaries, state.first_book_order, state.first_chapter ?? 1);
    const next = ordered[index + 1];
    const declaredEndKnown = state.last_chapter !== null && state.last_chapter !== undefined;
    const openEnded = !declaredEndKnown;
    let endGlobal = declaredEndKnown
      ? globalChapter(
          boundaries,
          state.last_book_order ?? state.first_book_order,
          state.last_chapter as number,
        )
      : total;
    if (next) {
      const nextStart = globalChapter(boundaries, next.first_book_order, next.first_chapter ?? 1);
      endGlobal = Math.min(endGlobal, Math.max(startGlobal, nextStart - 1));
    }
    return { state, startGlobal, endGlobal: Math.max(startGlobal, endGlobal), openEnded };
  });
};

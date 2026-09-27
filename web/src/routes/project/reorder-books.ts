import type { Book } from "@/lib/api";
import { sortedBooks } from "./project-lookup";

/** The full ordered id list `BookOrderUpdate` expects, from the current series order. */
export const orderOf = (books: readonly Book[]): string[] => {
  return sortedBooks(books).map((book) => book.id);
};

/** Moves one book up (`-1`) or down (`1`) a slot — the keyboard-operable equivalent of a drag. */
export const moveBook = (order: readonly string[], bookId: string, direction: -1 | 1): string[] => {
  const index = order.indexOf(bookId);
  const target = index + direction;
  if (index === -1 || target < 0 || target >= order.length) { return [...order]; }
  const next = [...order];
  const [removed] = next.splice(index, 1);
  next.splice(target, 0, removed as string);
  return next;
};

/** Moves `draggedId` to sit just before `targetId` — the drop side of a drag-and-drop reorder. */
export const moveBefore = (
  order: readonly string[],
  draggedId: string,
  targetId: string,
): string[] => {
  if (draggedId === targetId) { return [...order]; }
  const next = order.filter((id) => id !== draggedId);
  const targetIndex = next.indexOf(targetId);
  if (targetIndex === -1) { return [...order]; }
  next.splice(targetIndex, 0, draggedId);
  return next;
};

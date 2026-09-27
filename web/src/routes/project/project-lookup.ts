import type { Book } from "@/lib/api";

/** Books in series order — `series_order` is nullable (a standalone's one book), so unset sorts last rather than crashing a comparator. */
export const sortedBooks = (books: readonly Book[]): Book[] => {
  return [...books].sort(
    (a, b) => (a.series_order ?? Infinity) - (b.series_order ?? Infinity),
  );
};

export const bookById = (books: readonly Book[]): Map<string, Book> => {
  return new Map(books.map((book) => [book.id, book]));
};

export const bookBySeriesOrder = (books: readonly Book[]): Map<number, Book> => {
  const map = new Map<number, Book>();
  for (const book of books) {
    if (book.series_order !== null && book.series_order !== undefined) {
      map.set(book.series_order, book);
    }
  }
  return map;
};

/** The next open slot a newly-added book should default to — one past the highest series_order seen, or 1 for an empty project. */
export const nextSeriesOrder = (books: readonly Book[]): number => {
  const known = books
    .map((book) => book.series_order)
    .filter((order): order is number => order !== null && order !== undefined);
  return known.length === 0 ? 1 : Math.max(...known) + 1;
};

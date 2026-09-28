import { useParams } from "react-router";
import { ErrorState, LoadingSkeleton } from "@/components/ui";
import { useBook } from "@/lib/api";
import { limitsForBook, loadReadingPosition } from "@/lib/reading-position";
import { AskScreen } from "../ask/ask-screen";
import type { AskScope } from "../ask/types";

/**
 * A book-scoped ask defaults the reading position to this book
 * (`limit_book_order`) rather than leaving it unset — "no limit" has to be an
 * explicit choice at the call site (query-path.md), and defaulting a book
 * page's questions to the whole series would silently spoil later volumes.
 *
 * `/books/:id/*` sits outside `<ProjectLayout>`'s reading-position provider
 * (S8.6), so this reads the same `localStorage` entry directly rather than
 * duplicating a second, divergent position — `limitsForBook` derives this
 * book's own chapter cap (or "not reached yet"/"already finished") from
 * whatever the project's slider was last set to.
 */
export const BookAsk = () => {
  // Hooks.
  const { bookId = "" } = useParams();

  // Apis.
  const book = useBook(bookId);

  // Early returns.
  if (book.isPending) {
    return <LoadingSkeleton label="Loading" />;
  }
  if (book.error) {
    return <ErrorState error={book.error} onRetry={() => void book.refetch()} />;
  }

  const bookOrder = book.data.series_order ?? 1;
  const position = loadReadingPosition(book.data.project_id);
  const { limitBookOrder, limitChapter } = limitsForBook(position, bookOrder);

  const scope: AskScope = {
    projectId: book.data.project_id,
    limitBookOrder,
    limitChapter,
    label: limitChapter === null ? book.data.title : `${book.data.title} (up to chapter ${limitChapter})`,
    clearHref: `/projects/${book.data.project_id}/ask`,
  };

  return <AskScreen scope={scope} heading={`Ask about ${book.data.title}`} />;
};

export default BookAsk;

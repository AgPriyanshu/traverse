import { useParams } from "react-router";
import { ErrorState, LoadingSkeleton } from "@/components/ui";
import { useBook } from "@/lib/api";
import { AskScreen } from "../ask/ask-screen";
import type { AskScope } from "../ask/types";

/**
 * A book-scoped ask defaults the reading position to this book
 * (`limit_book_order`) rather than leaving it unset — "no limit" has to be an
 * explicit choice at the call site (query-path.md), and defaulting a book
 * page's questions to the whole series would silently spoil later volumes.
 * `limit_chapter` stays unset until Sprint 8's spoiler control exists.
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

  const scope: AskScope = {
    projectId: book.data.project_id,
    limitBookOrder: book.data.series_order ?? null,
    limitChapter: null,
    label: book.data.title,
    clearHref: `/projects/${book.data.project_id}/ask`,
  };

  return <AskScreen scope={scope} heading={`Ask about ${book.data.title}`} />;
};

export default BookAsk;

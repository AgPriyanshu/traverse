import { useParams } from "react-router";
import { ErrorState, LoadingSkeleton } from "@/components/ui";
import { useBook } from "@/lib/api";
import { ReviewQueue } from "../review/review-queue";

/**
 * Review tasks are project-wide (a `merge_across_books` task has no single
 * book), so this book route only resolves `project_id` and hands off — the
 * queue itself never takes a `book_id` filter.
 */
export const BookReview = () => {
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

  return <ReviewQueue projectId={book.data.project_id} heading="Review queue" />;
};

export default BookReview;

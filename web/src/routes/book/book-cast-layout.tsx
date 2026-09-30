import { Stack } from "@chakra-ui/react";
import { useMemo } from "react";
import { Outlet, useParams } from "react-router";
import { ErrorState, LoadingSkeleton } from "@/components/ui";
import type { Book } from "@/lib/api";
import { useBook, useProject } from "@/lib/api";
import { ProjectScopeContext } from "../project/project-scope";
import type { ProjectScope } from "../project/project-scope";
import { ProjectSpoilerSlider } from "../project/project-spoiler-slider";
import { ReadingPositionProvider } from "../project/reading-position-provider";

const EMPTY_BOOKS: Book[] = [];

/**
 * Characters and the graph, seen from inside one book. The screens are the
 * project's own, narrowed to this book, so a reader never leaves the book's
 * header and tabs to look at its cast.
 */
export const BookCastLayout = () => {
  // Hooks.
  const { bookId = "" } = useParams();

  // Apis.
  const book = useBook(bookId);
  const project = useProject(book.data?.project_id);

  // useMemos.
  const scope = useMemo<ProjectScope>(() => {
    return {
      projectId: book.data?.project_id ?? "",
      basePath: `/books/${bookId}`,
      bookId,
      bookOrder: book.data?.series_order ?? null,
    };
  }, [bookId, book.data?.project_id, book.data?.series_order]);

  // Early returns.
  if (book.error) {
    return <ErrorState error={book.error} onRetry={() => void book.refetch()} />;
  }

  if (!book.data) {
    return <LoadingSkeleton variant="text" count={6} label="Loading the book's cast" />;
  }

  return (
    <ProjectScopeContext.Provider value={scope}>
      <ReadingPositionProvider
        projectId={book.data.project_id}
        books={project.data?.books ?? EMPTY_BOOKS}
      >
        {project.data ? (
          <Stack gap="4" marginBlockEnd="7">
            <ProjectSpoilerSlider />
          </Stack>
        ) : null}

        <Outlet />
      </ReadingPositionProvider>
    </ProjectScopeContext.Provider>
  );
};

export default BookCastLayout;

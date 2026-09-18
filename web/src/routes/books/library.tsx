import { Button, SimpleGrid } from "@chakra-ui/react";
import { useMemo } from "react";
import { Link as RouterLink } from "react-router";
import { PageHeader } from "@/components/layout";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui";
import { useBooks, useProjects } from "@/lib/api";
import { BookCard } from "./book-card";
import { formatCount } from "@/lib/format";

const AddBookButton = () => {
  return (
    <Button
      asChild
      size="sm"
      bg="accent.solid"
      color="accent.contrast"
      borderRadius="md"
      _hover={{ opacity: 0.9 }}
    >
      <RouterLink to="/books/upload">Add a book</RouterLink>
    </Button>
  );
};

export const Library = () => {
  // Apis.
  const books = useBooks();
  const projects = useProjects();

  // useMemos.
  const projectsById = useMemo(() => {
    return new Map((projects.data ?? []).map((project) => [project.id, project]));
  }, [projects.data]);

  const sortedBooks = useMemo(() => {
    return [...(books.data ?? [])].sort((a, b) =>
      a.title.localeCompare(b.title),
    );
  }, [books.data]);

  // Variables.
  const isPending = books.isPending || projects.isPending;
  const error = books.error ?? projects.error ?? null;
  const showProject = (projects.data?.length ?? 0) > 1;

  // Handlers.
  const refetch = () => {
    void books.refetch();
    void projects.refetch();
  };

  return (
    <>
      <PageHeader
        title="Library"
        description="Every novel you have brought in, and what Traverse has made of it so far."
        meta={
          sortedBooks.length > 0
            ? formatCount(sortedBooks.length, "book")
            : undefined
        }
        actions={<AddBookButton />}
      />

      {isPending ? <LoadingSkeleton variant="cards" count={3} /> : null}

      {!isPending && error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : null}

      {!isPending && !error && sortedBooks.length === 0 ? (
        <EmptyState
          title="No books yet — upload a novel to begin"
          description="Traverse reads a PDF end to end, finds who is in it, and works out how they know each other. Every answer it gives points back at the page that proves it."
          action={<AddBookButton />}
        />
      ) : null}

      {sortedBooks.length > 0 ? (
        <SimpleGrid columns={{ base: 1, sm: 2, lg: 3 }} gap="4">
          {sortedBooks.map((book) => (
            <BookCard
              key={book.id}
              book={book}
              project={
                showProject ? projectsById.get(book.project_id) : undefined
              }
            />
          ))}
        </SimpleGrid>
      ) : null}
    </>
  );
};

export default Library;

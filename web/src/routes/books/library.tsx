import { Button, SimpleGrid } from "@chakra-ui/react";
import { useMemo } from "react";
import { Link as RouterLink } from "react-router";
import { PageHeader } from "@/components/layout";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui";
import { useLibrary } from "@/lib/api";
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
  const library = useLibrary();

  // useMemos.
  const projectsById = useMemo(() => {
    return new Map(library.projects.map((project) => [project.id, project]));
  }, [library.projects]);

  const books = useMemo(() => {
    return [...library.books].sort((a, b) => a.title.localeCompare(b.title));
  }, [library.books]);

  // Variables.
  const showProject = library.projects.length > 1;

  return (
    <>
      <PageHeader
        title="Library"
        description="Every novel you have brought in, and what Traverse has made of it so far."
        meta={
          books.length > 0 ? formatCount(books.length, "book") : undefined
        }
        actions={<AddBookButton />}
      />

      {library.isPending ? <LoadingSkeleton variant="cards" count={3} /> : null}

      {!library.isPending && library.error ? (
        <ErrorState error={library.error} onRetry={library.refetch} />
      ) : null}

      {!library.isPending && !library.error && books.length === 0 ? (
        <EmptyState
          title="No books yet — upload a novel to begin"
          description="Traverse reads a PDF end to end, finds who is in it, and works out how they know each other. Every answer it gives points back at the page that proves it."
          action={<AddBookButton />}
        />
      ) : null}

      {books.length > 0 ? (
        <SimpleGrid columns={{ base: 1, sm: 2, lg: 3 }} gap="4">
          {books.map((book) => (
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

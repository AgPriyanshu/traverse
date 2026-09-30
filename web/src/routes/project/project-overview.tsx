import { Box, Button, HStack, Heading, Link, Stack, Text } from "@chakra-ui/react";
import { useMemo, useState } from "react";
import type { DragEvent } from "react";
import { Link as RouterLink, useNavigate, useParams } from "react-router";
import { PageHeader } from "@/components/layout";
import {
  ConfirmDeleteButton,
  ErrorState,
  LoadingSkeleton,
  StatusDot,
  toaster,
  toneForBookStatus,
} from "@/components/ui";
import type { Book } from "@/lib/api";
import { useDeleteProject, useProject, useReorderBooks } from "@/lib/api";
import { formatCount, formatRelativeTime } from "@/lib/format";
import { AddBookForm } from "./add-book-form";
import { nextSeriesOrder, sortedBooks } from "./project-lookup";
import { moveBefore, moveBook, orderOf } from "./reorder-books";

const EMPTY_BOOKS: Book[] = [];

const BookRow = ({
  book,
  position,
  isFirst,
  isLast,
  onMove,
  onDragStart,
  onDragOver,
  onDrop,
}: {
  book: Book;
  position: number;
  isFirst: boolean;
  isLast: boolean;
  onMove: (direction: -1 | 1) => void;
  onDragStart: (event: DragEvent<HTMLDivElement>) => void;
  onDragOver: (event: DragEvent<HTMLDivElement>) => void;
  onDrop: (event: DragEvent<HTMLDivElement>) => void;
}) => {
  const status = toneForBookStatus(book.status);

  return (
    <Box
      as="li"
      draggable
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      borderTopWidth="1px"
      borderColor="border"
      paddingBlock="3.5"
      paddingInline="4"
      display="flex"
      alignItems="center"
      gap="4"
      cursor="grab"
    >
      <Text textStyle="data" color="fg.subtle" flex="0 0 2rem" aria-hidden="true">
        {position}.
      </Text>

      <Stack gap="0.5" flex="1" minWidth="0">
        <Link asChild fontWeight="600">
          <RouterLink to={`/books/${book.id}`}>{book.title}</RouterLink>
        </Link>
        <Text textStyle="data" color="fg.subtle">
          {[
            formatCount(book.page_count, "page"),
            formatCount(book.chapter_count, "chapter"),
            formatCount(book.character_count, "character"),
          ].join("  ·  ")}
        </Text>
      </Stack>

      <StatusDot tone={status.tone} label={status.label} />

      <Text textStyle="data" color="fg.subtle" whiteSpace="nowrap">
        {book.ingested_at ? formatRelativeTime(book.ingested_at) : "not ingested"}
      </Text>

      <HStack gap="1" role="group" aria-label={`Reorder ${book.title}`}>
        <Button
          size="xs"
          variant="outline"
          borderColor="border.control"
          color="fg"
          disabled={isFirst}
          aria-label={`Move ${book.title} earlier in the series`}
          onClick={() => { onMove(-1); }}
        >
          ↑
        </Button>
        <Button
          size="xs"
          variant="outline"
          borderColor="border.control"
          color="fg"
          disabled={isLast}
          aria-label={`Move ${book.title} later in the series`}
          onClick={() => { onMove(1); }}
        >
          ↓
        </Button>
      </HStack>
    </Box>
  );
};

/**
 * The books of a project in series order, drag-to-reorder (with an
 * up/down-button keyboard equivalent — a drag target alone is not
 * accessible), and adding a book with its series slot prefilled (S5.9).
 */
export const ProjectOverview = () => {
  // States.
  const [draggedId, setDraggedId] = useState<string | null>(null);

  // Hooks.
  const { projectId = "" } = useParams();
  const navigate = useNavigate();

  // Apis.
  const project = useProject(projectId);
  const reorder = useReorderBooks(projectId);
  const deleteProject = useDeleteProject();

  // useMemos.
  const books = useMemo(() => sortedBooks(project.data?.books ?? EMPTY_BOOKS), [project.data]);

  // Handlers.
  const submitOrder = (order: string[]) => {
    reorder.mutate({ order });
  };

  const handleMove = (bookId: string, direction: -1 | 1) => {
    submitOrder(moveBook(orderOf(books), bookId, direction));
  };

  const handleDragStart = (bookId: string) => (event: DragEvent<HTMLDivElement>) => {
    setDraggedId(bookId);
    event.dataTransfer.effectAllowed = "move";
  };

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
  };

  const handleDrop = (targetId: string) => (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (draggedId === null) { return; }
    submitOrder(moveBefore(orderOf(books), draggedId, targetId));
    setDraggedId(null);
  };

  // Early returns.
  if (project.isPending) {
    return <LoadingSkeleton variant="text" count={5} label="Loading project" />;
  }
  if (project.error) {
    return <ErrorState error={project.error} onRetry={() => void project.refetch()} />;
  }

  const data = project.data;
  const recomputing = reorder.isPending || project.isFetching;

  return (
    <>
      <PageHeader
        title={data.name}
        eyebrow={data.kind === "series" ? "Series" : "Standalone novel"}
        actions={
          <ConfirmDeleteButton
            label="Delete project"
            subject={`“${data.name}”`}
            consequences={`${
              books.length === 0
                ? "This project has no books."
                : `All ${formatCount(books.length, "book")} in it are removed, along with their PDFs, chapters, characters and relationships.`
            }`}
            isPending={deleteProject.isPending}
            onConfirm={() =>
              deleteProject.mutateAsync(projectId).then(
                () => {
                  toaster.create({ type: "success", title: "Project deleted" });
                  void navigate("/projects");
                },
                (error: unknown) => {
                  toaster.create({
                    type: "error",
                    title: "Could not delete the project",
                    description: error instanceof Error ? error.message : undefined,
                  });
                  throw error;
                },
              )
            }
          />
        }
        meta={
          <HStack gap="4" wrap="wrap">
            <Text textStyle="data" color="fg.subtle">
              {[
                formatCount(books.length, "book"),
                formatCount(data.character_count, "character"),
                formatCount(data.relation_count, "relationship"),
              ].join("  ·  ")}
            </Text>
          </HStack>
        }
      />

      <Stack gap="6">
        {recomputing ? (
          <Box
            role="status"
            borderWidth="1px"
            borderColor="accent.solid"
            bg="accent.subtle"
            borderRadius="md"
            paddingInline="4"
            paddingBlock="2.5"
          >
            <Text textStyle="small" color="accent.fg" fontWeight="600">
              Recomputing the roster and appearances for the new order…
            </Text>
          </Box>
        ) : null}

        {reorder.error ? (
          <ErrorState error={reorder.error} onRetry={() => { /* the row buttons resubmit on the next click */ }} title="Could not reorder" />
        ) : null}

        <Stack gap="3" as="section">
          <Heading as="h2" textStyle="subheading">
            Books, in series order
          </Heading>
          {books.length === 0 ? (
            <Text textStyle="body" color="fg.muted">
              No books yet — add the first one below.
            </Text>
          ) : (
            <Box
              as="ul"
              listStyleType="none"
              paddingInline="0"
              borderWidth="1px"
              borderColor="border"
              borderRadius="lg"
              bg="bg.surface"
              overflow="hidden"
            >
              {books.map((book, index) => (
                <BookRow
                  key={book.id}
                  book={book}
                  position={book.series_order ?? index + 1}
                  isFirst={index === 0}
                  isLast={index === books.length - 1}
                  onMove={(direction) => { handleMove(book.id, direction); }}
                  onDragStart={handleDragStart(book.id)}
                  onDragOver={handleDragOver}
                  onDrop={handleDrop(book.id)}
                />
              ))}
            </Box>
          )}
        </Stack>

        <Stack
          gap="3"
          as="section"
          borderWidth="1px"
          borderColor="border"
          borderRadius="lg"
          bg="bg.surface"
          padding="5"
        >
          <Heading as="h2" textStyle="subheading">
            Add a book
          </Heading>
          <AddBookForm projectId={projectId} suggestedOrder={nextSeriesOrder(books)} />
        </Stack>
      </Stack>
    </>
  );
};

export default ProjectOverview;

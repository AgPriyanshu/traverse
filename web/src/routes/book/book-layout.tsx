import { Box, HStack, Link, Text } from "@chakra-ui/react";
import { Link as RouterLink, Outlet, useNavigate, useParams } from "react-router";
import { NavLinks, PageHeader, bookNav } from "@/components/layout";
import { ConfirmDeleteButton, StatusDot, toaster, toneForBookStatus } from "@/components/ui";
import { useBook, useDeleteBook, useProject } from "@/lib/api";
import { formatCount, formatRelativeTime } from "@/lib/format";

export const BookLayout = () => {
  // Hooks.
  const { bookId = "" } = useParams();
  const navigate = useNavigate();

  // Apis.
  const book = useBook(bookId);
  const project = useProject(book.data?.project_id);
  const deleteBook = useDeleteBook();

  // Variables.
  const status = book.data ? toneForBookStatus(book.data.status) : null;

  return (
    <>
      <PageHeader
        title={book.data?.title ?? "Book"}
        actions={
          book.data ? (
            <ConfirmDeleteButton
              label="Delete book"
              subject={`“${book.data.title}”`}
              consequences="The PDF, its chapters and pages, and every character and relationship found only in this book are removed. If it is the last book in its project, the project is deleted too."
              isPending={deleteBook.isPending}
              onConfirm={() =>
                deleteBook.mutateAsync(bookId).then(
                  () => {
                    toaster.create({ type: "success", title: "Book deleted" });
                    void navigate("/books");
                  },
                  (error: unknown) => {
                    toaster.create({
                      type: "error",
                      title: "Could not delete the book",
                      description: error instanceof Error ? error.message : undefined,
                    });
                    throw error;
                  },
                )
              }
            />
          ) : undefined
        }
        eyebrow={
          project.data ? (
            <Link asChild>
              <RouterLink to={`/projects/${project.data.id}`}>{project.data.name}</RouterLink>
            </Link>
          ) : (
            book.data?.author ?? undefined
          )
        }
        meta={
          <HStack gap="4" wrap="wrap">
            {status ? (
              <StatusDot tone={status.tone} label={status.label} />
            ) : null}
            <Text textStyle="data" color="fg.subtle">
              {[
                formatCount(book.data?.page_count, "page"),
                formatCount(book.data?.chapter_count, "chapter"),
              ].join("  ·  ")}
            </Text>
            {book.data?.ingested_at ? (
              <Text textStyle="data" color="fg.subtle">
                ingested {formatRelativeTime(book.data.ingested_at)}
              </Text>
            ) : null}
          </HStack>
        }
      />

      <Box
        marginBlockEnd="7"
        paddingBlockEnd="1"
        borderBottomWidth="1px"
        borderColor="border"
      >
        <NavLinks
          items={bookNav(bookId, book.data?.project_id)}
          direction="row"
          ariaLabel="This book"
        />
      </Box>

      <Outlet />
    </>
  );
};

export default BookLayout;

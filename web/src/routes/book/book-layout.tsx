import { Box, HStack, Link, Text } from "@chakra-ui/react";
import { Link as RouterLink, Outlet, useParams } from "react-router";
import { NavLinks, PageHeader, bookNav } from "@/components/layout";
import { StatusDot, toneForBookStatus } from "@/components/ui";
import { useBook, useProject } from "@/lib/api";
import { formatCount, formatRelativeTime } from "@/lib/format";

export const BookLayout = () => {
  // Hooks.
  const { bookId = "" } = useParams();

  // Apis.
  const book = useBook(bookId);
  const project = useProject(book.data?.project_id);

  // Variables.
  const status = book.data ? toneForBookStatus(book.data.status) : null;

  return (
    <>
      <PageHeader
        title={book.data?.title ?? "Book"}
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

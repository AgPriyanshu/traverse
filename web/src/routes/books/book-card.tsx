import { Box, HStack, Heading, Stack, Text } from "@chakra-ui/react";
import { Link as RouterLink } from "react-router";
import { StatusDot, toneForBookStatus } from "@/components/ui";
import type { Book, Project } from "@/lib/api";
import { formatCount, formatRelativeTime } from "@/lib/format";

export type BookCardProps = {
  book: Book;
  /** Shown only when the library holds more than one project. */
  project?: Project;
};

export const BookCard = ({ book, project }: BookCardProps) => {
  // Variables.
  const status = toneForBookStatus(book.status);

  return (
    <Box
      asChild
      borderWidth="1px"
      borderColor="border"
      borderRadius="lg"
      bg="bg.surface"
      padding="5"
      transitionProperty="border-color, box-shadow"
      transitionDuration="fast"
      _hover={{ borderColor: "border.control", boxShadow: "card" }}
    >
      <RouterLink to={`/books/${book.id}`}>
        <Stack gap="3" height="full">
          {project ? (
            <Text textStyle="data" color="fg.subtle" truncate>
              {project.name}
            </Text>
          ) : null}

          <Stack gap="1" flex="1" minWidth="0">
            <Heading as="h3" textStyle="subheading" color="fg">
              {book.title}
            </Heading>
            {book.author ? (
              <Text textStyle="small" color="fg.muted" truncate>
                {book.author}
              </Text>
            ) : null}
          </Stack>

          <Text textStyle="data" color="fg.subtle">
            {[
              formatCount(book.page_count, "page"),
              formatCount(book.chapter_count, "chapter"),
              formatCount(book.character_count, "character"),
            ].join("  ·  ")}
          </Text>

          <HStack
            justify="space-between"
            gap="3"
            paddingBlockStart="3"
            borderTopWidth="1px"
            borderColor="border"
          >
            <StatusDot tone={status.tone} label={status.label} />
            <Text textStyle="data" color="fg.subtle" whiteSpace="nowrap">
              {book.ingested_at
                ? formatRelativeTime(book.ingested_at)
                : "not ingested"}
            </Text>
          </HStack>
        </Stack>
      </RouterLink>
    </Box>
  );
};

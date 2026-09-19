import { Box, Button, Drawer, HStack, Portal, Stack, Text } from "@chakra-ui/react";
import { useQueries } from "@tanstack/react-query";
import { useState } from "react";
import { ErrorState, LoadingSkeleton, PageRef } from "@/components/ui";
import type { Chapter } from "@/lib/api";
import { chunksQueryOptions } from "@/lib/api";
import { formatChapterLabel, formatCount } from "@/lib/format";

// The contract has no `chapter_id` filter on `GET /books/{id}/chunks` yet
// (SCR-2) — this pages through the book's chunks (500 at a time, the
// server's own cap) and filters client-side, stopping once it has at least
// as many matches as the chapter's own `chunk_count` says exist.
const PAGE_SIZE = 500;

export type ChunkInspectorProps = {
  bookId: string;
  chapter: Chapter | null;
  onClose: () => void;
};

export const ChunkInspector = ({
  bookId,
  chapter,
  onClose,
}: ChunkInspectorProps) => {
  // States.
  const [pageCount, setPageCount] = useState(1);
  // Not an effect: React's own pattern for resetting state when a prop
  // changes — a render-phase setState, processed before the browser paints,
  // rather than a post-commit effect that would flash the stale page count.
  const [trackedChapterId, setTrackedChapterId] = useState(chapter?.id);
  if (chapter?.id !== trackedChapterId) {
    setTrackedChapterId(chapter?.id);
    setPageCount(1);
  }

  // Apis.
  const pages = useQueries({
    queries: chapter
      ? Array.from({ length: pageCount }, (_unused, index) => ({
          ...chunksQueryOptions(bookId, {
            limit: PAGE_SIZE,
            offset: index * PAGE_SIZE,
          }),
        }))
      : [],
  });

  // Variables.
  const isFirstLoad = pages.length > 0 && pages[0].isPending;
  const isFetchingMore = pages.some((page) => page.isFetching);
  const firstError = pages.find((page) => page.error)?.error;
  const lastPage = pages[pages.length - 1];
  const matching = pages
    .flatMap((page) => page.data ?? [])
    .filter((chunk) => chunk.chapter_id === chapter?.id);
  const fetchedEverything =
    lastPage?.data !== undefined && lastPage.data.length < PAGE_SIZE;
  const hasEnoughMatches = chapter ? matching.length >= chapter.chunk_count : true;
  const canLoadMore = !fetchedEverything && !hasEnoughMatches && !isFirstLoad;

  return (
    <Drawer.Root
      open={chapter !== null}
      placement="end"
      onOpenChange={(details) => {
        if (!details.open) { onClose(); }
      }}
    >
      <Portal>
        <Drawer.Backdrop />
        <Drawer.Positioner>
          <Drawer.Content bg="bg.surface" maxW={{ base: "full", sm: "md" }}>
            <Drawer.Header borderBottomWidth="1px" borderColor="border">
              <Drawer.Title textStyle="subheading" color="fg">
                {chapter ? formatChapterLabel(chapter.number, chapter.title) : ""}
              </Drawer.Title>
              <Text textStyle="data" color="fg.subtle">
                {chapter ? formatCount(chapter.chunk_count, "chunk") : ""}
              </Text>
            </Drawer.Header>

            <Drawer.Body>
              <Stack gap="0">
                {isFirstLoad ? (
                  <Box paddingBlock="4">
                    <LoadingSkeleton variant="rows" count={4} label="Loading chunks" />
                  </Box>
                ) : null}

                {firstError ? (
                  <Box paddingBlock="4">
                    <ErrorState error={firstError} />
                  </Box>
                ) : null}

                {!isFirstLoad && !firstError && matching.length === 0 ? (
                  <Text textStyle="body" color="fg.muted" paddingBlock="4">
                    No chunks reported for this chapter yet.
                  </Text>
                ) : null}

                {matching.map((chunk) => (
                  <Stack
                    key={chunk.id}
                    gap="2"
                    borderBottomWidth="1px"
                    borderColor="border"
                    paddingBlock="4"
                  >
                    <HStack justify="space-between" wrap="wrap" gap="2">
                      <PageRef
                        page={chunk.page_start}
                        pageEnd={chunk.page_end}
                        bookId={bookId}
                      />
                      {chunk.token_count !== null && chunk.token_count !== undefined ? (
                        <Text textStyle="data" color="fg.subtle">
                          {formatCount(chunk.token_count, "token")}
                        </Text>
                      ) : null}
                    </HStack>

                    <Text textStyle="body" color="fg" lineClamp={4}>
                      {chunk.text}
                    </Text>

                    {chunk.dense_score !== null && chunk.dense_score !== undefined ? (
                      <HStack gap="4">
                        <Text textStyle="data" color="fg.subtle">
                          dense {chunk.dense_score.toFixed(3)}
                        </Text>
                        {chunk.lexical_score !== null &&
                        chunk.lexical_score !== undefined ? (
                          <Text textStyle="data" color="fg.subtle">
                            lexical {chunk.lexical_score.toFixed(3)}
                          </Text>
                        ) : null}
                      </HStack>
                    ) : null}
                  </Stack>
                ))}

                {canLoadMore ? (
                  <Box paddingBlockStart="4">
                    <Button
                      size="sm"
                      variant="outline"
                      borderColor="border.control"
                      color="fg"
                      borderRadius="md"
                      loading={isFetchingMore}
                      onClick={() => { setPageCount((current) => current + 1); }}
                    >
                      Load more chunks
                    </Button>
                  </Box>
                ) : null}
              </Stack>
            </Drawer.Body>

            <Drawer.CloseTrigger asChild>
              <Button
                size="sm"
                variant="ghost"
                position="absolute"
                top="3"
                right="3"
                color="fg.muted"
                onClick={onClose}
              >
                Close
              </Button>
            </Drawer.CloseTrigger>
          </Drawer.Content>
        </Drawer.Positioner>
      </Portal>
    </Drawer.Root>
  );
};

export default ChunkInspector;

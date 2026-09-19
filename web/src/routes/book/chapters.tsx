import { Badge, Box, Button, HStack, Heading, Stack, Text } from "@chakra-ui/react";
import { useState } from "react";
import { useParams } from "react-router";
import { EmptyState, ErrorState, LoadingSkeleton, PageRef } from "@/components/ui";
import type { Chapter } from "@/lib/api";
import { useChapters } from "@/lib/api";
import { formatChapterLabel, formatCount } from "@/lib/format";
import { ChunkInspector } from "./chunk-inspector";

const DETECTION_LABEL: Record<Chapter["detection_method"], string> = {
  regex: "regex",
  llm: "llm",
  manual: "manual",
};

/** A debugging affordance for the team and a trust signal for the reader — how confident chapter detection was. */
const DetectionBadge = ({ method }: { method: Chapter["detection_method"] }) => {
  return (
    <Badge
      textStyle="data"
      color="fg.subtle"
      bg="bg.sunken"
      borderWidth="1px"
      borderColor="border"
      borderRadius="full"
      paddingInline="2"
      textTransform="lowercase"
    >
      {DETECTION_LABEL[method]}
    </Badge>
  );
};

export const Chapters = () => {
  // States.
  const [openChapter, setOpenChapter] = useState<Chapter | null>(null);

  // Hooks.
  const { bookId = "" } = useParams();

  // Apis.
  const chapters = useChapters(bookId);

  return (
    <Stack gap="7" maxW="measure">
      <Stack gap="2">
        <Heading as="h2" textStyle="heading">
          Chapters
        </Heading>
        <Text textStyle="body" color="fg.muted">
          Every chapter Traverse found, with the pages it spans and how it was
          detected. Open a chapter to inspect the chunks it was cut into.
        </Text>
      </Stack>

      {chapters.isPending ? (
        <LoadingSkeleton variant="rows" count={5} label="Loading chapters" />
      ) : null}

      {chapters.error ? (
        <ErrorState
          error={chapters.error}
          onRetry={() => void chapters.refetch()}
        />
      ) : null}

      {!chapters.isPending && !chapters.error && chapters.data?.length === 0 ? (
        <EmptyState
          title="No chapters yet"
          description="Chapter segmentation runs early in ingestion — check the overview tab for where this book's run stands."
        />
      ) : null}

      {chapters.data && chapters.data.length > 0 ? (
        <Stack gap="0" as="ol" listStyleType="none" paddingInline="0">
          {chapters.data.map((chapter) => (
            <HStack
              key={chapter.id}
              as="li"
              justify="space-between"
              align="center"
              gap="4"
              borderBottomWidth="1px"
              borderColor="border"
              paddingBlock="4"
              wrap="wrap"
            >
              <Stack gap="1" minWidth="0">
                <Text textStyle="body" color="fg">
                  {formatChapterLabel(chapter.number, chapter.title)}
                </Text>
                <HStack gap="3" wrap="wrap">
                  <PageRef
                    page={chapter.page_start}
                    pageEnd={chapter.page_end}
                    bookId={bookId}
                  />
                  <DetectionBadge method={chapter.detection_method} />
                </HStack>
              </Stack>

              <Box flexShrink="0">
                <Button
                  size="sm"
                  variant="outline"
                  borderColor="border.control"
                  color="fg"
                  borderRadius="md"
                  onClick={() => { setOpenChapter(chapter); }}
                >
                  {formatCount(chapter.chunk_count, "chunk")}
                </Button>
              </Box>
            </HStack>
          ))}
        </Stack>
      ) : null}

      <ChunkInspector
        bookId={bookId}
        chapter={openChapter}
        onClose={() => { setOpenChapter(null); }}
      />
    </Stack>
  );
};

export default Chapters;

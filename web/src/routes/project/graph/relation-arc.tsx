import { Box, HStack, Stack, Text } from "@chakra-ui/react";
import { useMemo } from "react";
import { ErrorState, LoadingSkeleton, PageRef } from "@/components/ui";
import type { Book, Relation } from "@/lib/api";
import { useRelationArc } from "@/lib/api";
import { bookBySeriesOrder } from "../project-lookup";
import { buildBoundaries, buildSegments, totalGlobalChapters } from "./arc-segments";
import type { ArcSegment, BookBoundary } from "./arc-segments";
import { FamilyBadge } from "./family-stroke";
import {
  FAMILY_COLOR_VAR,
  FAMILY_DASH,
  predicateLabel,
} from "./relation-style";

const positionText = (segment: ArcSegment, boundaries: readonly BookBoundary[]): string => {
  const startBook = boundaries.find((b) => b.startGlobal <= segment.startGlobal && segment.startGlobal <= b.endGlobal);
  const bookLabel = startBook ? `bk. ${startBook.book.series_order}` : "";
  const chapterInBook = startBook ? segment.startGlobal - startBook.startGlobal + 1 : segment.startGlobal;
  if (segment.openEnded) { return `${bookLabel} ch. ${chapterInBook}–end`; }
  return `${bookLabel} ch. ${chapterInBook}`;
};

/** The page ref that best represents where a state begins — the one in its own first book, when several are cited. */
const citationFor = (state: Relation, booksBySeriesOrder: ReadonlyMap<number, Book>) => {
  const refs = state.page_refs ?? [];
  const inFirstBook = refs.find((ref) => ref.book_order === state.first_book_order);
  const ref = inFirstBook ?? refs[0];
  if (!ref) { return null; }
  const book = booksBySeriesOrder.get(ref.book_order);
  return { page: ref.page, bookId: ref.book_id ?? book?.id, bookTitle: book?.title };
};

export type RelationArcViewProps = {
  states: readonly Relation[];
  books: readonly Book[];
};

export const RelationArcView = ({ states, books }: RelationArcViewProps) => {
  // useMemos.
  const boundaries = useMemo(() => buildBoundaries(books), [books]);
  const booksBySeriesOrder = useMemo(() => bookBySeriesOrder(books), [books]);
  const segments = useMemo(() => buildSegments(states, boundaries), [states, boundaries]);

  // Variables.
  const total = totalGlobalChapters(boundaries);
  const percent = (globalChapter: number) => ((globalChapter - 1) / total) * 100;
  const multiBook = boundaries.length > 1;

  if (segments.length === 0) {
    return (
      <Text textStyle="small" color="fg.muted">
        No relationship states recorded for this pair.
      </Text>
    );
  }

  return (
    <Stack gap="3">
      <Box
        position="relative"
        height="6"
        role="img"
        aria-label={segments
          .map(
            (segment) =>
              `${predicateLabel(segment.state.predicate)}, ${positionText(segment, boundaries)}`,
          )
          .join("; then ")}
      >
        {multiBook
          ? boundaries.slice(1).map((boundary) => (
              <Box
                key={boundary.book.id}
                position="absolute"
                top="-1"
                bottom="-1"
                width="1px"
                bg="border"
                style={{ left: `${percent(boundary.startGlobal)}%` }}
                aria-hidden="true"
              />
            ))
          : null}
        {segments.map((segment, index) => {
          const left = percent(segment.startGlobal);
          const width = ((segment.endGlobal - segment.startGlobal + 1) / total) * 100;
          const family = segment.state.family;
          return (
            <Box
              key={segment.state.id}
              position="absolute"
              top="0"
              bottom="0"
              style={{ left: `${left}%`, width: `${width}%` }}
              paddingInline="0.5"
              data-testid="arc-segment"
            >
              <svg
                width="100%"
                height="100%"
                aria-hidden="true"
                focusable="false"
                preserveAspectRatio="none"
              >
                <line
                  x1="0"
                  y1="50%"
                  x2="100%"
                  y2="50%"
                  stroke={FAMILY_COLOR_VAR[family]}
                  strokeWidth={5}
                  strokeLinecap="butt"
                  strokeDasharray={FAMILY_DASH[family].join(" ") || undefined}
                />
              </svg>
              <Box
                position="absolute"
                top="50%"
                left="0"
                transform="translate(-50%, -50%)"
                width="4"
                height="4"
                borderRadius="full"
                bg="bg.surface"
                borderWidth="2px"
                borderColor="fg"
                display="flex"
                alignItems="center"
                justifyContent="center"
                aria-hidden="true"
              >
                <Text as="span" textStyle="small" fontSize="2xs" lineHeight="1" color="fg">
                  {index + 1}
                </Text>
              </Box>
            </Box>
          );
        })}
      </Box>

      {multiBook ? (
        <HStack justify="space-between">
          {boundaries.map((boundary) => (
            <Text key={boundary.book.id} textStyle="data" color="fg.subtle">
              bk. {boundary.book.series_order} — {boundary.book.title}
            </Text>
          ))}
        </HStack>
      ) : null}

      <Stack as="ol" gap="2" listStyleType="none" margin="0" padding="0">
        {segments.map((segment, index) => {
          const citation = citationFor(segment.state, booksBySeriesOrder);
          return (
            <Box as="li" key={segment.state.id} display="flex" gap="2.5" alignItems="baseline" flexWrap="wrap">
              <Text textStyle="data" color="fg.subtle" aria-hidden="true">
                {index + 1}
              </Text>
              <Text textStyle="body" fontWeight="600">
                {predicateLabel(segment.state.predicate)}
              </Text>
              <Text textStyle="small" color="fg.muted">
                {positionText(segment, boundaries)}
              </Text>
              <FamilyBadge family={segment.state.family} />
              {index > 0 ? (
                <Text textStyle="small" color="fg.subtle">
                  begins
                </Text>
              ) : null}
              {citation ? (
                <PageRef page={citation.page} bookId={citation.bookId} bookTitle={citation.bookTitle} />
              ) : (
                <Text textStyle="small" color="status.warn">
                  no page cited
                </Text>
              )}
            </Box>
          );
        })}
      </Stack>
    </Stack>
  );
};

export type RelationArcProps = {
  a: string;
  b: string;
  books: readonly Book[];
};

/** Fetches the pair's arc and renders it; nothing at all when the API has none, since an empty arc is not a fact. */
export const RelationArc = ({ a, b, books }: RelationArcProps) => {
  // Apis.
  const arc = useRelationArc(a, b);

  if (arc.isPending) {
    return <LoadingSkeleton variant="text" count={2} label="Loading relationship arc" />;
  }
  if (arc.error) {
    return <ErrorState error={arc.error} onRetry={() => void arc.refetch()} />;
  }

  return (
    <Stack gap="2" as="section" aria-label="Relationship arc">
      <HStack justify="space-between">
        <Text textStyle="small" color="fg.subtle" fontWeight="600" textTransform="uppercase" letterSpacing="wide">
          How it changes
        </Text>
      </HStack>
      <RelationArcView states={arc.data.states ?? []} books={books} />
    </Stack>
  );
};

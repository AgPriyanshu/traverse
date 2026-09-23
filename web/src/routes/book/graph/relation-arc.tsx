import { Box, HStack, Stack, Text } from "@chakra-ui/react";
import { useMemo } from "react";
import { ErrorState, LoadingSkeleton, PageRef } from "@/components/ui";
import type { Relation } from "@/lib/api";
import { useRelationArc } from "@/lib/api";
import { buildSegments } from "./arc-segments";
import type { ArcSegment } from "./arc-segments";
import { FamilyBadge } from "./family-stroke";
import {
  FAMILY_COLOR_VAR,
  FAMILY_DASH,
  predicateLabel,
} from "./relation-style";

const chapterSpanText = (segment: ArcSegment): string => {
  if (segment.openEnded) { return `ch. ${segment.start}–end`; }
  if (segment.start === segment.end) { return `ch. ${segment.start}`; }
  return `ch. ${segment.start}–${segment.end}`;
};

export type RelationArcViewProps = {
  states: readonly Relation[];
  chapterCount: number;
  bookId: string;
  bookTitle?: string | null;
};

export const RelationArcView = ({
  states,
  chapterCount,
  bookId,
  bookTitle,
}: RelationArcViewProps) => {
  // useMemos.
  const segments = useMemo(() => buildSegments(states, chapterCount), [states, chapterCount]);

  // Variables.
  const total = Math.max(
    1,
    chapterCount,
    ...segments.map((segment) => segment.end),
  );
  const percent = (chapter: number) => ((chapter - 1) / total) * 100;

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
              `${predicateLabel(segment.state.predicate)}, ${chapterSpanText(segment)}`,
          )
          .join("; then ")}
      >
        {segments.map((segment, index) => {
          const left = percent(segment.start);
          const width = ((segment.end - segment.start + 1) / total) * 100;
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

      <Stack as="ol" gap="2" listStyleType="none" margin="0" padding="0">
        {segments.map((segment, index) => {
          const ref = segment.state.page_refs?.[0];
          return (
            <Box as="li" key={segment.state.id} display="flex" gap="2.5" alignItems="baseline" flexWrap="wrap">
              <Text textStyle="data" color="fg.subtle" aria-hidden="true">
                {index + 1}
              </Text>
              <Text textStyle="body" fontWeight="600">
                {predicateLabel(segment.state.predicate)}
              </Text>
              <Text textStyle="small" color="fg.muted">
                {chapterSpanText(segment)}
              </Text>
              <FamilyBadge family={segment.state.family} />
              {index > 0 ? (
                <Text textStyle="small" color="fg.subtle">
                  begins
                </Text>
              ) : null}
              {ref ? (
                <PageRef
                  page={ref.page}
                  bookId={ref.book_id ?? bookId}
                  bookTitle={bookTitle}
                />
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
  chapterCount: number;
  bookId: string;
  bookTitle?: string | null;
};

/** Fetches the pair's arc and renders it; nothing at all when the API has none, since an empty arc is not a fact. */
export const RelationArc = ({ a, b, chapterCount, bookId, bookTitle }: RelationArcProps) => {
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
      <RelationArcView
        states={arc.data.states ?? []}
        chapterCount={chapterCount}
        bookId={bookId}
        bookTitle={bookTitle}
      />
    </Stack>
  );
};

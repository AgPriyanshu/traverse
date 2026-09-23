import { Box, HStack, Span, Text } from "@chakra-ui/react";
import { PageRef } from "@/components/ui";
import type { AssertionType, Evidence } from "@/lib/api";

const ASSERTION_LABEL: Record<AssertionType, string> = {
  narrated: "narrated",
  dialogue: "dialogue",
  inferred: "inferred",
};

const ASSERTION_MARK: Record<AssertionType, string> = {
  narrated: "¶",
  dialogue: "“ ”",
  inferred: "~",
};

/** Not decoration: hearsay and inference must read differently from narrated fact at a glance (design/DESIGN.md §4). */
export const AssertionBadge = ({ type }: { type: AssertionType }) => {
  const isFact = type === "narrated";
  return (
    <Span
      textStyle="small"
      fontWeight="600"
      color={isFact ? "fg.muted" : "status.warn"}
      borderWidth="1px"
      borderColor={isFact ? "border" : "status.warn"}
      borderStyle={type === "inferred" ? "dashed" : "solid"}
      borderRadius="sm"
      paddingInline="1.5"
      whiteSpace="nowrap"
    >
      <Span aria-hidden="true">{ASSERTION_MARK[type]} </Span>
      {ASSERTION_LABEL[type]}
    </Span>
  );
};

export type EvidenceItemProps = {
  evidence: Evidence;
  bookTitle?: string | null;
};

export const EvidenceItem = ({ evidence, bookTitle }: EvidenceItemProps) => {
  return (
    <Box as="li" borderTopWidth="1px" borderColor="border" paddingBlock="3.5">
      <Text as="blockquote" textStyle="quote" fontStyle="italic" margin="0">
        {evidence.quote}
      </Text>
      <HStack gap="2.5" wrap="wrap" marginBlockStart="2">
        <PageRef
          page={evidence.page_start}
          pageEnd={evidence.page_end}
          bookId={evidence.book_id}
          bookTitle={evidence.book_title ?? bookTitle}
        />
        {evidence.chapter_no !== null && evidence.chapter_no !== undefined ? (
          <Text textStyle="small" color="fg.muted">
            chapter {evidence.chapter_no}
          </Text>
        ) : null}
        <AssertionBadge type={evidence.assertion_type} />
        {evidence.assertion_type === "dialogue" && evidence.asserted_by ? (
          <Text textStyle="small" color="fg.muted">
            said by {evidence.asserted_by}
          </Text>
        ) : null}
      </HStack>
    </Box>
  );
};

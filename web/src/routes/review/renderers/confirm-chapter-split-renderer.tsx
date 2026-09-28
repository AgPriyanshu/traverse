import { Badge, Box, Button, HStack, Stack, Text } from "@chakra-ui/react";
import { PageRef } from "@/components/ui";
import type { ConfirmChapterSplitPayload, DetectionMethod } from "@/lib/api";
import { formatChapterLabel } from "@/lib/format";
import { useTaskShortcuts } from "../shortcuts-context";
import type { Decision } from "../types";

const DETECTION_LABEL: Record<DetectionMethod, string> = {
  regex: "heading pattern",
  llm: "model judgement",
  manual: "human reviewed",
};

export type ConfirmChapterSplitRendererProps = {
  payload: ConfirmChapterSplitPayload;
  onResolve: (decision: Decision) => void;
};

export const ConfirmChapterSplitRenderer = ({ payload, onResolve }: ConfirmChapterSplitRendererProps) => {
  // Variables.
  const { chapter } = payload;

  // Handlers.
  const accept = () => {
    onResolve({ decision: "accept", payload: {}, label: "Confirmed chapter boundary" });
  };

  const reject = () => {
    onResolve({ decision: "reject", payload: {}, label: "Rejected chapter boundary" });
  };

  useTaskShortcuts({ a: accept, r: reject });

  return (
    <Stack gap="5">
      <Stack gap="1.5">
        <HStack gap="3" wrap="wrap">
          <Text textStyle="heading" color="fg">
            {formatChapterLabel(chapter.number, chapter.title)}
          </Text>
          <PageRef page={chapter.page_start} pageEnd={chapter.page_end} bookId={chapter.book_id} />
        </HStack>
        <HStack gap="3" wrap="wrap">
          <Badge bg="bg.sunken" color="fg.muted" borderRadius="md" paddingInline="2" textStyle="data">
            {DETECTION_LABEL[chapter.detection_method]}
          </Badge>
          {payload.confidence !== null && payload.confidence !== undefined ? (
            <Text textStyle="data" color="fg.subtle">{Math.round(payload.confidence * 100)}% confidence</Text>
          ) : null}
        </HStack>
      </Stack>

      <Stack gap="3">
        <Box>
          <Text textStyle="small" fontWeight="600" color="fg.muted" marginBlockEnd="1">Before the split</Text>
          <Text textStyle="quote" fontStyle="italic" color="fg.muted" borderInlineStartWidth="2px" borderColor="border" paddingInlineStart="3">
            {payload.preceding_text}
          </Text>
        </Box>
        <Box>
          <Text textStyle="small" fontWeight="600" color="fg.muted" marginBlockEnd="1">After the split</Text>
          <Text textStyle="quote" fontStyle="italic" color="fg.muted" borderInlineStartWidth="2px" borderColor="border" paddingInlineStart="3">
            {payload.following_text}
          </Text>
        </Box>
      </Stack>

      <HStack gap="3">
        <Button size="sm" variant="solid" bg="accent.solid" color="accent.contrast" borderRadius="md" onClick={accept}>
          Confirm split (a)
        </Button>
        <Button size="sm" variant="outline" borderColor="border.control" color="fg" borderRadius="md" onClick={reject}>
          Not a chapter break (r)
        </Button>
      </HStack>
    </Stack>
  );
};

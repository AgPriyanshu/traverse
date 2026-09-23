import { Box, Button, Drawer, HStack, Portal, Span, Stack, Text } from "@chakra-ui/react";
import { useMemo, useState } from "react";
import { ErrorState, LoadingSkeleton } from "@/components/ui";
import { useEvidence } from "@/lib/api";
import { formatCount } from "@/lib/format";
import type { EdgeContext } from "./edge-context";
import { EvidenceItem } from "./evidence-item";
import { FamilyBadge } from "./family-stroke";
import { RelationArc } from "./relation-arc";
import { predicateLabel } from "./relation-style";

const EVIDENCE_PAGE_SIZE = 10;

export type EvidencePanelProps = {
  target: EdgeContext | null;
  bookId: string;
  bookTitle?: string | null;
  chapterCount: number;
  onClose: () => void;
};

export const EvidencePanel = ({
  target,
  bookId,
  bookTitle,
  chapterCount,
  onClose,
}: EvidencePanelProps) => {
  return (
    <Drawer.Root
      open={target !== null}
      placement="end"
      onOpenChange={(details) => {
        if (!details.open) { onClose(); }
      }}
    >
      <Portal>
        <Drawer.Backdrop />
        <Drawer.Positioner>
          <Drawer.Content bg="bg.surface" maxW={{ base: "full", sm: "lg" }}>
            {target ? (
              <EvidenceBody
                key={target.edge.id}
                target={target}
                bookId={bookId}
                bookTitle={bookTitle}
                chapterCount={chapterCount}
                onClose={onClose}
              />
            ) : null}
          </Drawer.Content>
        </Drawer.Positioner>
      </Portal>
    </Drawer.Root>
  );
};

type EvidenceBodyProps = Omit<EvidencePanelProps, "target"> & { target: EdgeContext };

const EvidenceBody = ({
  target,
  bookId,
  bookTitle,
  chapterCount,
  onClose,
}: EvidenceBodyProps) => {
  const { edge, sourceName, targetName } = target;

  // States.
  const [offset, setOffset] = useState(0);

  // Apis.
  const evidence = useEvidence(edge.id, { limit: EVIDENCE_PAGE_SIZE, offset });

  // useMemos.
  const items = useMemo(() => {
    return [...(evidence.data ?? [])].sort(
      (a, b) =>
        (a.chapter_no ?? Infinity) - (b.chapter_no ?? Infinity) ||
        a.page_start - b.page_start,
    );
  }, [evidence.data]);

  // Variables.
  const total = Math.max(edge.evidence_count, offset + items.length);
  const hasPrevious = offset > 0;
  const hasNext = offset + EVIDENCE_PAGE_SIZE < edge.evidence_count;

  return (
    <>
      <Drawer.Header borderBottomWidth="1px" borderColor="border">
        <Stack gap="2" flex="1" minWidth="0">
          <Drawer.Title textStyle="subheading" color="fg">
            {sourceName}
            <Span color="fg.muted"> — {predicateLabel(edge.predicate)} → </Span>
            {targetName}
          </Drawer.Title>
          <HStack gap="3" wrap="wrap">
            <FamilyBadge family={edge.family} />
            <Text textStyle="data" color="fg.muted">
              confidence {Math.round(edge.confidence * 100)}%
            </Text>
            <Text textStyle="data" color="fg.muted">
              {formatCount(edge.evidence_count, "citation")}
            </Text>
          </HStack>
          {edge.hearsay ? (
            <Text textStyle="small" color="status.warn" fontWeight="600">
              Hearsay: this is asserted in dialogue, not stated by the narrator.
            </Text>
          ) : null}
        </Stack>
        <Drawer.CloseTrigger asChild>
          <Button size="sm" variant="ghost" color="fg" onClick={onClose}>
            Close
          </Button>
        </Drawer.CloseTrigger>
      </Drawer.Header>

      <Drawer.Body>
        <Stack gap="5">
          <RelationArc
            a={edge.source}
            b={edge.target}
            chapterCount={chapterCount}
            bookId={bookId}
            bookTitle={bookTitle}
          />

          <Stack gap="0" as="section" aria-label="Evidence">
            <Text textStyle="small" color="fg.subtle" fontWeight="600" textTransform="uppercase" letterSpacing="wide" marginBlockEnd="1">
              The pages that say so
            </Text>
            {evidence.isPending ? (
              <LoadingSkeleton variant="rows" count={3} label="Loading evidence" />
            ) : null}
            {evidence.error ? (
              <ErrorState error={evidence.error} onRetry={() => void evidence.refetch()} />
            ) : null}
            {!evidence.isPending && !evidence.error && items.length === 0 ? (
              <Text textStyle="body" color="fg.muted">
                No evidence items came back for this relation.
              </Text>
            ) : null}
            <Box as="ol" listStyleType="none" margin="0" padding="0">
              {items.map((item) => (
                <EvidenceItem key={item.id} evidence={item} bookTitle={bookTitle} />
              ))}
            </Box>
          </Stack>

          {hasPrevious || hasNext ? (
            <HStack justify="space-between">
              <Button
                size="sm"
                variant="outline"
                borderColor="border.control"
                color="fg"
                disabled={!hasPrevious}
                onClick={() => { setOffset(Math.max(0, offset - EVIDENCE_PAGE_SIZE)); }}
              >
                Earlier
              </Button>
              <Text textStyle="data" color="fg.muted" aria-live="polite">
                {offset + 1}–{offset + items.length} of {total}
              </Text>
              <Button
                size="sm"
                variant="outline"
                borderColor="border.control"
                color="fg"
                disabled={!hasNext}
                onClick={() => { setOffset(offset + EVIDENCE_PAGE_SIZE); }}
              >
                Later
              </Button>
            </HStack>
          ) : null}
        </Stack>
      </Drawer.Body>
    </>
  );
};

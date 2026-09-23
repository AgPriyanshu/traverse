import { Box, Button, HStack, Link, Stack, Text } from "@chakra-ui/react";
import { useMemo } from "react";
import { Link as RouterLink, useSearchParams } from "react-router";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui";
import type { Chapter, GraphEdge, RelationFamily } from "@/lib/api";
import { useNeighbourhood } from "@/lib/api";
import { formatCount } from "@/lib/format";
import { buildNodeIndex, contextFor } from "./edge-context";
import { EvidencePanel } from "./evidence-panel";
import { FamilyBadge } from "./family-stroke";
import { edgeChapterSpan } from "./graph-filters";
import { FAMILY_LABEL, FAMILY_ORDER, predicateLabel } from "./relation-style";

export type CharacterRelationshipsProps = {
  characterId: string;
  bookId: string;
  bookTitle?: string | null;
  chapters: readonly Chapter[];
  chapterCount: number;
};

/** A character's relationships grouped by family; each row opens the same evidence panel the graph uses (S4.13). */
export const CharacterRelationships = ({
  characterId,
  bookId,
  bookTitle,
  chapters,
  chapterCount,
}: CharacterRelationshipsProps) => {
  // Hooks.
  const [searchParams, setSearchParams] = useSearchParams();

  // Apis.
  const hood = useNeighbourhood(characterId, 1);

  // useMemos.
  const nodeIndex = useMemo(() => buildNodeIndex(hood.data), [hood.data]);
  const groups = useMemo(() => {
    const edges = (hood.data?.edges ?? []).filter(
      (edge) => edge.source === characterId || edge.target === characterId,
    );
    const byFamily = new Map<RelationFamily, GraphEdge[]>();
    for (const edge of edges) {
      const bucket = byFamily.get(edge.family) ?? [];
      bucket.push(edge);
      byFamily.set(edge.family, bucket);
    }
    return FAMILY_ORDER.filter((family) => byFamily.has(family)).map((family) => ({
      family,
      edges: (byFamily.get(family) ?? []).sort((a, b) => b.evidence_count - a.evidence_count),
    }));
  }, [hood.data, characterId]);

  // Variables.
  const selectedEdgeId = searchParams.get("edge");
  const selected = useMemo(() => {
    const edge = (hood.data?.edges ?? []).find((candidate) => candidate.id === selectedEdgeId);
    return edge ? contextFor(edge, nodeIndex) : null;
  }, [hood.data, selectedEdgeId, nodeIndex]);

  // Handlers.
  const handleSelect = (edgeId: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (edgeId === null) {
      next.delete("edge");
    } else {
      next.set("edge", edgeId);
    }
    setSearchParams(next, { replace: true });
  };

  if (hood.isPending) {
    return <LoadingSkeleton variant="rows" count={3} label="Loading relationships" />;
  }
  if (hood.error) {
    return <ErrorState error={hood.error} onRetry={() => void hood.refetch()} />;
  }
  if (groups.length === 0) {
    return (
      <EmptyState
        title="No relationships yet"
        description="Nothing has been extracted for this character, or every candidate lacked a page citation."
      />
    );
  }

  return (
    <Stack gap="4">
      {groups.map(({ family, edges }) => (
        <Stack key={family} as="section" gap="1" aria-label={`${FAMILY_LABEL[family]} relationships`}>
          <FamilyBadge family={family} />
          <Stack as="ul" gap="0" listStyleType="none" margin="0" padding="0">
            {edges.map((edge) => {
              const outgoing = edge.source === characterId;
              const otherId = outgoing ? edge.target : edge.source;
              const otherName = nodeIndex.get(otherId)?.canonical_name ?? "Unknown character";
              const span = edgeChapterSpan(edge, chapters);
              return (
                <Box
                  as="li"
                  key={edge.id}
                  borderTopWidth="1px"
                  borderColor="border"
                  paddingBlock="2"
                >
                  <HStack gap="2" wrap="wrap" align="baseline">
                    <Link asChild fontWeight="600">
                      <RouterLink to={`/books/${bookId}/characters/${otherId}`}>
                        {otherName}
                      </RouterLink>
                    </Link>
                    <Text textStyle="small" color="fg.muted">
                      {outgoing ? `${predicateLabel(edge.predicate)} →` : `← ${predicateLabel(edge.predicate)}`}
                    </Text>
                  </HStack>
                  <HStack gap="3" wrap="wrap" justify="space-between" marginBlockStart="1">
                    <Text textStyle="data" color="fg.muted">
                      {formatCount(edge.evidence_count, "citation")}
                      {span ? ` · ch. ${span.first}–${span.last}` : ""}
                      {edge.hearsay ? " · hearsay" : ""}
                    </Text>
                    <Button
                      size="xs"
                      variant="outline"
                      borderColor="border.control"
                      color="fg"
                      aria-label={`Evidence for ${predicateLabel(edge.predicate)} ${otherName}`}
                      onClick={() => { handleSelect(edge.id); }}
                    >
                      Evidence
                    </Button>
                  </HStack>
                </Box>
              );
            })}
          </Stack>
        </Stack>
      ))}

      <EvidencePanel
        target={selected}
        bookId={bookId}
        bookTitle={bookTitle}
        chapterCount={chapterCount}
        onClose={() => { handleSelect(null); }}
      />
    </Stack>
  );
};

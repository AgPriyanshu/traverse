import { Box, Button, HStack, Heading, Link, Stack, Text } from "@chakra-ui/react";
import { useMemo } from "react";
import { Link as RouterLink } from "react-router";
import type { Chapter, GraphEdge, GraphNode } from "@/lib/api";
import { formatCount } from "@/lib/format";
import { TIER_ORDER } from "../character-labels";
import { CharacterTierBadge } from "../character-tier-badge";
import { FamilyBadge } from "./family-stroke";
import { edgeChapterSpan } from "./graph-filters";
import { predicateLabel } from "./relation-style";

export type GraphListViewProps = {
  nodes: readonly GraphNode[];
  edges: readonly GraphEdge[];
  chapters: readonly Chapter[];
  bookId: string;
  onSelectEdge: (edge: GraphEdge) => void;
};

/** The non-visual equivalent of the graph: same filtered data, same click-through, and the better view on a phone. */
export const GraphListView = ({
  nodes,
  edges,
  chapters,
  bookId,
  onSelectEdge,
}: GraphListViewProps) => {
  // useMemos.
  const groups = useMemo(() => {
    const byId = new Map(nodes.map((node) => [node.id, node]));
    const perNode = new Map<string, GraphEdge[]>();
    for (const edge of edges) {
      for (const id of [edge.source, edge.target]) {
        const bucket = perNode.get(id) ?? [];
        bucket.push(edge);
        perNode.set(id, bucket);
      }
    }
    return nodes
      .filter((node) => perNode.has(node.id))
      .sort(
        (a, b) =>
          TIER_ORDER.indexOf(a.importance_tier) - TIER_ORDER.indexOf(b.importance_tier) ||
          b.mention_count - a.mention_count,
      )
      .map((node) => ({
        node,
        items: (perNode.get(node.id) ?? [])
          .map((edge) => {
            const outgoing = edge.source === node.id;
            const other = byId.get(outgoing ? edge.target : edge.source);
            return { edge, outgoing, other };
          })
          .sort((a, b) => b.edge.evidence_count - a.edge.evidence_count),
      }));
  }, [nodes, edges]);

  if (groups.length === 0) {
    return (
      <Text textStyle="body" color="fg.muted">
        No relationships match these filters.
      </Text>
    );
  }

  return (
    <Stack as="ul" gap="4" listStyleType="none" margin="0" padding="0" aria-label="Relationships by character">
      {groups.map(({ node, items }) => (
        <Box
          as="li"
          key={node.id}
          borderWidth="1px"
          borderColor="border"
          borderRadius="lg"
          bg="bg.surface"
          padding="4"
        >
          <HStack gap="3" wrap="wrap" marginBlockEnd="2">
            <Heading as="h3" textStyle="subheading">
              <Link asChild>
                <RouterLink to={`/books/${bookId}/characters/${node.id}`}>
                  {node.canonical_name}
                </RouterLink>
              </Link>
            </Heading>
            <CharacterTierBadge tier={node.importance_tier} />
            <Text textStyle="data" color="fg.subtle">
              {formatCount(items.length, "relationship")}
            </Text>
          </HStack>
          <Stack as="ul" gap="0" listStyleType="none" margin="0" padding="0">
            {items.map(({ edge, outgoing, other }) => {
              const span = edgeChapterSpan(edge, chapters);
              return (
                <Box
                  as="li"
                  key={edge.id}
                  borderTopWidth="1px"
                  borderColor="border"
                  paddingBlock="2"
                  display="flex"
                  gap="3"
                  alignItems="center"
                  flexWrap="wrap"
                >
                  <Text textStyle="small" color="fg.muted" flex="0 0 auto">
                    {outgoing ? `${predicateLabel(edge.predicate)} →` : `← ${predicateLabel(edge.predicate)}`}
                  </Text>
                  <Link asChild flex="1 1 8rem" minWidth="0">
                    <RouterLink to={`/books/${bookId}/characters/${other?.id ?? ""}`}>
                      {other?.canonical_name ?? "Unknown character"}
                    </RouterLink>
                  </Link>
                  <FamilyBadge family={edge.family} />
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
                    aria-label={`Evidence for ${node.canonical_name} ${predicateLabel(edge.predicate)} ${other?.canonical_name ?? ""}`}
                    onClick={() => { onSelectEdge(edge); }}
                  >
                    Evidence
                  </Button>
                </Box>
              );
            })}
          </Stack>
        </Box>
      ))}
    </Stack>
  );
};

import { Badge, Box, Button, HStack, Stack, Text } from "@chakra-ui/react";
import { useState } from "react";
import { PageRef } from "@/components/ui";
import type { Character, MergePayload, Mention } from "@/lib/api";
import { formatAliasRun } from "@/lib/format";
import { CharacterTierBadge } from "../../project/character-tier-badge";
import { RESOLUTION_METHOD_LABEL } from "../../project/character-labels";
import { useTaskShortcuts } from "../shortcuts-context";
import type { Decision } from "../types";

const bestPrimary = (candidates: readonly Character[]): string => {
  return [...candidates].sort((a, b) => b.mention_count - a.mention_count)[0]?.id ?? "";
};

const MentionContext = ({ mention }: { mention: Mention }) => {
  return (
    <Box as="li" borderTopWidth="1px" borderColor="border" paddingBlock="2.5">
      <HStack gap="2" wrap="wrap" marginBlockEnd="1">
        <Text textStyle="small" fontWeight="600" color="fg">
          {mention.surface_form}
        </Text>
        <PageRef page={mention.page} bookId={mention.book_id} />
        <Text textStyle="small" color="fg.subtle">
          {RESOLUTION_METHOD_LABEL[mention.resolution_method]}
        </Text>
      </HStack>
      {mention.context ? (
        <Text textStyle="quote" fontStyle="italic" color="fg.muted">
          {mention.context}
        </Text>
      ) : null}
    </Box>
  );
};

export type MergeRendererProps = {
  payload: MergePayload;
  onResolve: (decision: Decision) => void;
};

/**
 * The "two Catherines" renderer — one column per candidate so the reviewer
 * sees *why the system is unsure* before deciding, never a bare confirm
 * dialog. Shared by `merge_characters` and `merge_across_books`: same shape,
 * different scope (design/DESIGN.md's brief for S7.9).
 */
export const MergeRenderer = ({ payload, onResolve }: MergeRendererProps) => {
  // States.
  const [primaryId, setPrimaryId] = useState(() => bestPrimary(payload.candidates));
  const [mergeIds, setMergeIds] = useState<Set<string>>(
    () => new Set(payload.candidates.filter((c) => c.id !== primaryId).map((c) => c.id)),
  );

  // Variables.
  const primary = payload.candidates.find((c) => c.id === primaryId) ?? payload.candidates[0];

  // Handlers.
  const makePrimary = (id: string) => {
    setPrimaryId(id);
    setMergeIds(new Set(payload.candidates.filter((c) => c.id !== id).map((c) => c.id)));
  };

  const toggleMerge = (id: string) => {
    setMergeIds((previous) => {
      const next = new Set(previous);
      if (next.has(id)) { next.delete(id); } else { next.add(id); }
      return next;
    });
  };

  const merge = () => {
    if (!primary || mergeIds.size === 0) { return; }
    onResolve({
      decision: "merge",
      payload: { primary_id: primary.id, merge_ids: [...mergeIds] },
      label: `Merged into ${primary.canonical_name}`,
    });
  };

  const keepSeparate = () => {
    onResolve({ decision: "keep_separate", payload: {}, label: "Kept separate" });
  };

  useTaskShortcuts({ m: merge, s: keepSeparate });

  return (
    <Stack gap="5">
      <HStack gap="3" wrap="wrap">
        <Text textStyle="body" color="fg.muted">
          {payload.candidates.length} candidates, {payload.candidates.reduce((sum, c) => sum + c.mention_count, 0)} mentions total.
        </Text>
        {payload.similarity_score !== null && payload.similarity_score !== undefined ? (
          <Badge bg="bg.sunken" color="fg.muted" borderRadius="md" paddingInline="2" textStyle="data">
            {Math.round(payload.similarity_score * 100)}% similar
          </Badge>
        ) : null}
      </HStack>

      <HStack gap="4" wrap="wrap" alignItems="stretch">
        {payload.candidates.map((candidate) => {
          const isPrimary = candidate.id === primaryId;
          const willMerge = mergeIds.has(candidate.id);
          const mentions = payload.contexts?.[candidate.id] ?? [];

          return (
            <Stack
              key={candidate.id}
              gap="3"
              flex="1"
              minW="17rem"
              borderWidth="1px"
              borderColor={isPrimary ? "accent.solid" : "border"}
              borderRadius="lg"
              bg="bg.surface"
              padding="4"
            >
              <Stack gap="1.5">
                <HStack justify="space-between" wrap="wrap">
                  <Text textStyle="heading" color="fg">
                    {candidate.canonical_name}
                  </Text>
                  <CharacterTierBadge tier={candidate.importance_tier} />
                </HStack>
                {candidate.aliases && candidate.aliases.length > 0 ? (
                  <Text textStyle="small" fontStyle="italic" color="fg.muted">
                    {formatAliasRun(candidate.aliases)}
                  </Text>
                ) : null}
                <HStack gap="2" textStyle="data" color="fg.subtle">
                  {candidate.first_page !== null && candidate.first_page !== undefined ? (
                    <>
                      first seen{" "}
                      <PageRef page={candidate.first_page} bookId={candidate.first_book_id} />
                    </>
                  ) : null}
                  <Text as="span">{candidate.mention_count} mentions</Text>
                </HStack>
              </Stack>

              <HStack gap="2" wrap="wrap">
                <Button
                  size="xs"
                  variant="outline"
                  aria-pressed={isPrimary}
                  borderColor={isPrimary ? "accent.solid" : "border.control"}
                  bg={isPrimary ? "accent.subtle" : "transparent"}
                  color="fg"
                  onClick={() => { makePrimary(candidate.id); }}
                >
                  Keep as this one
                </Button>
                {!isPrimary ? (
                  <Button
                    size="xs"
                    variant="outline"
                    aria-pressed={willMerge}
                    borderColor={willMerge ? "accent.solid" : "border.control"}
                    bg={willMerge ? "accent.subtle" : "transparent"}
                    color="fg"
                    onClick={() => { toggleMerge(candidate.id); }}
                  >
                    {willMerge ? "Merging in" : "Merge in"}
                  </Button>
                ) : null}
              </HStack>

              <Stack as="ul" gap="0" maxH="20rem" overflowY="auto">
                {mentions.length === 0 ? (
                  <Text textStyle="small" color="fg.subtle">No contexts provided.</Text>
                ) : (
                  mentions.map((mention) => <MentionContext key={mention.id} mention={mention} />)
                )}
              </Stack>
            </Stack>
          );
        })}
      </HStack>

      <HStack gap="3">
        <Button
          size="sm"
          variant="solid"
          bg="accent.solid"
          color="accent.contrast"
          borderRadius="md"
          disabled={mergeIds.size === 0}
          onClick={merge}
        >
          Merge (m)
        </Button>
        <Button
          size="sm"
          variant="outline"
          borderColor="border.control"
          color="fg"
          borderRadius="md"
          onClick={keepSeparate}
        >
          Keep separate (s)
        </Button>
      </HStack>
    </Stack>
  );
};

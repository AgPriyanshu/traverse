import { Box, Button, HStack, Stack, Text } from "@chakra-ui/react";
import type { ResolveConflictPayload } from "@/lib/api";
import { FamilyBadge } from "../../project/graph/family-stroke";
import { EvidenceItem } from "../../project/graph/evidence-item";
import { predicateLabel } from "../../project/graph/relation-style";
import { useTaskShortcuts } from "../shortcuts-context";
import type { Decision } from "../types";

export type ResolveConflictRendererProps = {
  payload: ResolveConflictPayload;
  onResolve: (decision: Decision) => void;
};

/**
 * Side-by-side contradicting evidence. "Mark as a temporal transition" is
 * often the right answer (the brief's own note) — it accepts every conflicting
 * relation in the order the aggregator produced them, rather than forcing a
 * single winner, and is one key (`t`) precisely so it doesn't lose to the
 * pick-one path by being harder to reach.
 */
export const ResolveConflictRenderer = ({ payload, onResolve }: ResolveConflictRendererProps) => {
  // Handlers.
  const acceptOne = (relationId: string, subjectObject: string) => {
    onResolve({
      decision: "accept",
      payload: { relation_id: relationId },
      label: `Kept ${subjectObject}`,
    });
  };

  const markTemporal = () => {
    onResolve({
      decision: "temporal_transition",
      payload: { order: payload.conflicting.map((relation) => relation.id) },
      label: "Marked as a temporal transition",
    });
  };

  const numberHandlers = Object.fromEntries(
    payload.conflicting.slice(0, 9).map((relation, index) => [
      String(index + 1),
      () => { acceptOne(relation.id, `${relation.subject_name} ${predicateLabel(relation.predicate)} ${relation.object_name}`); },
    ]),
  );

  useTaskShortcuts({ ...numberHandlers, t: markTemporal });

  return (
    <Stack gap="5">
      <Text textStyle="body" color="fg.muted">{payload.reason}</Text>

      <HStack gap="4" wrap="wrap" alignItems="stretch">
        {payload.conflicting.map((relation, index) => (
          <Stack
            key={relation.id}
            gap="3"
            flex="1"
            minW="17rem"
            borderWidth="1px"
            borderColor="border"
            borderRadius="lg"
            bg="bg.surface"
            padding="4"
          >
            <HStack justify="space-between" wrap="wrap">
              <Text textStyle="heading" color="fg">
                {relation.subject_name} {predicateLabel(relation.predicate)} {relation.object_name}
              </Text>
              <Text textStyle="data" color="fg.subtle">{index + 1}</Text>
            </HStack>
            <HStack gap="3" wrap="wrap">
              <FamilyBadge family={relation.family} />
              <Text textStyle="data" color="fg.subtle">{Math.round(relation.confidence * 100)}% confidence</Text>
              {relation.status !== "active" ? (
                <Text textStyle="small" color="fg.muted">{relation.status}</Text>
              ) : null}
            </HStack>
            <Box>
              <Stack as="ul" gap="0" maxH="16rem" overflowY="auto">
                {(payload.evidence?.[relation.id] ?? []).map((item) => (
                  <EvidenceItem key={item.id} evidence={item} />
                ))}
              </Stack>
            </Box>
            <Button
              size="sm"
              variant="solid"
              bg="accent.solid"
              color="accent.contrast"
              borderRadius="md"
              onClick={() => { acceptOne(relation.id, `${relation.subject_name} ${predicateLabel(relation.predicate)} ${relation.object_name}`); }}
            >
              This one is correct ({index + 1})
            </Button>
          </Stack>
        ))}
      </HStack>

      <Box>
        <Button
          size="sm"
          variant="outline"
          borderColor="border.control"
          color="fg"
          borderRadius="md"
          onClick={markTemporal}
        >
          Both true, at different times (t)
        </Button>
      </Box>
    </Stack>
  );
};

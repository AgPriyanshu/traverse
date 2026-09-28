import { Box, Button, HStack, Stack, Text, chakra } from "@chakra-ui/react";
import { useRef, useState } from "react";
import type { ConfirmRelationPayload } from "@/lib/api";
import { useOntology } from "@/lib/api";
import { FamilyBadge } from "../../project/graph/family-stroke";
import { EvidenceItem } from "../../project/graph/evidence-item";
import { predicateLabel } from "../../project/graph/relation-style";
import { useTaskShortcuts } from "../shortcuts-context";
import type { Decision } from "../types";

const Select = chakra("select");

export type ConfirmRelationRendererProps = {
  payload: ConfirmRelationPayload;
  onResolve: (decision: Decision) => void;
};

export const ConfirmRelationRenderer = ({ payload, onResolve }: ConfirmRelationRendererProps) => {
  // Refs.
  const selectRef = useRef<HTMLSelectElement>(null);

  // States.
  const [predicate, setPredicate] = useState(payload.relation.predicate);

  // Apis.
  const ontology = useOntology();

  // Variables.
  const { relation } = payload;
  const predicates = ontology.data?.predicates ?? [];
  const evidence = payload.evidence ?? [];

  // Handlers.
  const accept = () => {
    onResolve({ decision: "accept", payload: {}, label: "Accepted relation" });
  };

  const reject = () => {
    onResolve({ decision: "reject", payload: {}, label: "Rejected relation" });
  };

  const changePredicate = () => {
    if (predicate === relation.predicate) {
      selectRef.current?.focus();
      return;
    }
    onResolve({
      decision: "change_predicate",
      payload: { predicate },
      label: `Changed predicate to ${predicateLabel(predicate)}`,
    });
  };

  useTaskShortcuts({ a: accept, r: reject, e: changePredicate });

  return (
    <Stack gap="5">
      <Stack gap="2">
        <HStack gap="2.5" wrap="wrap">
          <Text textStyle="heading" color="fg">
            {relation.subject_name}
          </Text>
          <Text textStyle="body" color="accent.fg" fontWeight="600">
            {predicateLabel(relation.predicate)}
          </Text>
          <Text textStyle="heading" color="fg">
            {relation.object_name}
          </Text>
        </HStack>
        <HStack gap="3" wrap="wrap">
          <FamilyBadge family={relation.family} />
          <Text textStyle="data" color="fg.subtle">
            {Math.round(relation.confidence * 100)}% confidence
          </Text>
          {relation.hearsay ? (
            <Text textStyle="small" color="status.warn">hearsay</Text>
          ) : null}
        </HStack>
        <Text textStyle="body" color="fg.muted">{payload.reason}</Text>
      </Stack>

      <Box>
        <Text textStyle="subheading" color="fg" marginBlockEnd="1">
          Evidence
        </Text>
        <Stack as="ul" gap="0">
          {evidence.length === 0 ? (
            <Text textStyle="small" color="fg.subtle">No evidence attached.</Text>
          ) : (
            evidence.map((item) => <EvidenceItem key={item.id} evidence={item} />)
          )}
        </Stack>
      </Box>

      <HStack gap="3" wrap="wrap" alignItems="flex-end">
        <Button size="sm" variant="solid" bg="accent.solid" color="accent.contrast" borderRadius="md" onClick={accept}>
          Accept (a)
        </Button>
        <Button size="sm" variant="outline" borderColor="border.control" color="fg" borderRadius="md" onClick={reject}>
          Reject (r)
        </Button>
        <Stack gap="1">
          <Text asChild textStyle="small" color="fg.muted">
            <label htmlFor="predicate-select">Or change the predicate (e)</label>
          </Text>
          <HStack gap="2">
            <Select
              id="predicate-select"
              ref={selectRef}
              value={predicate}
              onChange={(event) => { setPredicate(event.target.value); }}
              borderWidth="1px"
              borderColor="border.control"
              borderRadius="md"
              bg="bg.surface"
              paddingInline="2"
              paddingBlock="1"
              textStyle="body"
              color="fg"
            >
              {predicates.length === 0 ? <option value={relation.predicate}>{predicateLabel(relation.predicate)}</option> : null}
              {predicates.map((p) => (
                <option key={p.predicate} value={p.predicate}>{predicateLabel(p.predicate)}</option>
              ))}
            </Select>
            <Button
              size="sm"
              variant="outline"
              borderColor="border.control"
              color="fg"
              borderRadius="md"
              disabled={predicate === relation.predicate}
              onClick={changePredicate}
            >
              Change
            </Button>
          </HStack>
        </Stack>
      </HStack>
    </Stack>
  );
};

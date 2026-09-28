import { Badge, Box, Button, HStack, Stack, Text } from "@chakra-ui/react";
import { PageRef } from "@/components/ui";
import type { CandidateKind, ClassifyCandidatePayload } from "@/lib/api";
import { CANDIDATE_KIND_LABEL } from "../task-meta";
import { useTaskShortcuts } from "../shortcuts-context";
import type { Decision } from "../types";

const KIND_KEY: Record<CandidateKind, string> = {
  person: "c",
  place: "p",
  organisation: "o",
  unknown: "n",
};

export type ClassifyCandidateRendererProps = {
  payload: ClassifyCandidatePayload;
  onResolve: (decision: Decision) => void;
};

export const ClassifyCandidateRenderer = ({ payload, onResolve }: ClassifyCandidateRendererProps) => {
  // Variables.
  const contexts = payload.contexts ?? [];

  // Handlers.
  const classify = (kind: CandidateKind) => {
    onResolve({
      decision: "classify",
      payload: { kind },
      label: `Classified as ${CANDIDATE_KIND_LABEL[kind].toLowerCase()}`,
    });
  };

  const acceptGuess = () => {
    if (payload.kind_guess) { classify(payload.kind_guess); }
  };

  useTaskShortcuts({
    c: () => { classify("person"); },
    p: () => { classify("place"); },
    o: () => { classify("organisation"); },
    n: () => { classify("unknown"); },
    ...(payload.kind_guess ? { a: acceptGuess } : {}),
  });

  return (
    <Stack gap="5">
      <Stack gap="1.5">
        <Text textStyle="heading" color="fg">{payload.surface_form}</Text>
        <Text textStyle="data" color="fg.subtle">{payload.mention_count} mentions</Text>
        {payload.kind_guess ? (
          <HStack gap="2">
            <Badge bg="bg.sunken" color="fg.muted" borderRadius="md" paddingInline="2" textStyle="data">
              model guess: {CANDIDATE_KIND_LABEL[payload.kind_guess]}
            </Badge>
          </HStack>
        ) : null}
      </Stack>

      <Box>
        <Text textStyle="subheading" color="fg" marginBlockEnd="1">Contexts</Text>
        <Stack as="ul" gap="0" maxH="20rem" overflowY="auto">
          {contexts.length === 0 ? (
            <Text textStyle="small" color="fg.subtle">No contexts provided.</Text>
          ) : (
            contexts.map((mention) => (
              <Box key={mention.id} as="li" borderTopWidth="1px" borderColor="border" paddingBlock="2.5">
                <HStack gap="2" marginBlockEnd="1">
                  <PageRef page={mention.page} bookId={mention.book_id} />
                </HStack>
                {mention.context ? (
                  <Text textStyle="quote" fontStyle="italic" color="fg.muted">{mention.context}</Text>
                ) : null}
              </Box>
            ))
          )}
        </Stack>
      </Box>

      <HStack gap="3" wrap="wrap">
        {payload.kind_guess ? (
          <Button size="sm" variant="solid" bg="accent.solid" color="accent.contrast" borderRadius="md" onClick={acceptGuess}>
            Accept guess (a)
          </Button>
        ) : null}
        {(["person", "place", "organisation", "unknown"] as const).map((kind) => (
          <Button
            key={kind}
            size="sm"
            variant="outline"
            borderColor="border.control"
            color="fg"
            borderRadius="md"
            onClick={() => { classify(kind); }}
          >
            {CANDIDATE_KIND_LABEL[kind]} ({KIND_KEY[kind]})
          </Button>
        ))}
      </HStack>
    </Stack>
  );
};

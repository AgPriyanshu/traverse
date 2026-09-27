import { Box, HStack, Stack, Text } from "@chakra-ui/react";
import { InterruptCard, StatusDot } from "@/components/ui";
import { CitationMark } from "./citation-mark";
import { RouteBadge } from "./route-badge";
import type { Turn } from "./types";

export type TurnViewProps = {
  turn: Turn;
  onRespondToInterrupt: (turnId: string, answer: string) => void;
};

/** One question/answer pair — the unit `<ConversationThread>` repeats (S6.13). */
export const TurnView = ({ turn, onRespondToInterrupt }: TurnViewProps) => {
  // Variables.
  const hasAnswer = turn.parts.length > 0;
  const isThinking = turn.status === "streaming" && !hasAnswer;

  return (
    <Stack gap="3" as="article" aria-label={`Question: ${turn.question}`}>
      <Text textStyle="subheading" color="fg">
        {turn.question}
      </Text>

      {isThinking ? (
        <HStack gap="2">
          <StatusDot tone="busy" label="Thinking" />
        </HStack>
      ) : null}

      {hasAnswer ? (
        <Text
          as="div"
          textStyle="quote"
          color="fg"
          maxW="measure"
          data-testid="answer-text"
        >
          {turn.parts.map((part) =>
            part.kind === "text" ? (
              <Text as="span" key={part.id}>
                {part.text}
              </Text>
            ) : (
              <CitationMark key={part.id} index={part.index} citation={part.citation} />
            ),
          )}
        </Text>
      ) : null}

      {turn.status === "interrupt" && turn.interrupt ? (
        <InterruptCard
          question={turn.interrupt.question}
          options={turn.interrupt.options}
          onSelectOption={(option) => { onRespondToInterrupt(turn.id, option); }}
          onSubmitText={(text) => { onRespondToInterrupt(turn.id, text); }}
        />
      ) : null}

      {turn.status === "error" ? (
        <Box
          role="alert"
          borderWidth="1px"
          borderColor={turn.errorRecoverable ? "border" : "status.err"}
          borderRadius="md"
          bg="bg.sunken"
          padding="3"
        >
          <Text textStyle="small" color={turn.errorRecoverable ? "fg.muted" : "status.err"}>
            {turn.errorMessage ?? "Something went wrong answering this."}
          </Text>
        </Box>
      ) : null}

      <HStack gap="4" wrap="wrap">
        {turn.route ? <RouteBadge route={turn.route} /> : null}
        {turn.status === "done" && turn.abstained ? (
          <StatusDot tone="idle" label="Not established in the text" />
        ) : null}
      </HStack>
    </Stack>
  );
};

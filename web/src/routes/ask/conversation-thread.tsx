import { Box, Button, Separator, Stack } from "@chakra-ui/react";
import { useEffect, useRef } from "react";
import { plainTextOf } from "./types";
import type { Turn } from "./types";
import { TurnView } from "./turn-view";

export type ConversationThreadProps = {
  turns: Turn[];
  onRespondToInterrupt: (turnId: string, answer: string) => void;
};

/** Turns with their citations, scroll-anchored, copyable (S6.13). */
export const ConversationThread = ({ turns, onRespondToInterrupt }: ConversationThreadProps) => {
  // Refs.
  const endRef = useRef<HTMLDivElement>(null);

  // Variables.
  const lastTurn = turns[turns.length - 1];
  const lastTurnPartCount = lastTurn?.parts.length;
  const lastTurnStatus = lastTurn?.status;

  // useEffects.
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [turns.length, lastTurnPartCount, lastTurnStatus]);

  // Handlers.
  const handleCopy = (turn: Turn) => {
    const text = plainTextOf(turn.parts);
    try {
      void navigator.clipboard?.writeText(text);
    } catch {
      // Clipboard access can be denied or unavailable — copying is a
      // convenience, not something worth surfacing an error for.
    }
  };

  return (
    <Stack gap="6" role="log" aria-label="Conversation">
      {turns.map((turn, index) => (
        <Box key={turn.id}>
          {index > 0 ? <Separator borderColor="border" marginBlockEnd="6" /> : null}
          <TurnView turn={turn} onRespondToInterrupt={onRespondToInterrupt} />
          {turn.status === "done" ? (
            <Button
              size="xs"
              variant="ghost"
              color="fg.subtle"
              paddingInline="0"
              marginBlockStart="2"
              onClick={() => { handleCopy(turn); }}
            >
              Copy answer
            </Button>
          ) : null}
        </Box>
      ))}
      <div ref={endRef} />
    </Stack>
  );
};

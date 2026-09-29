import { Heading, Stack, Text } from "@chakra-ui/react";
import { useEffect, useRef } from "react";
import { AskComposer } from "./ask-composer";
import { ConversationThread } from "./conversation-thread";
import { InferenceModeNote } from "./inference-mode-note";
import { ScopeBanner } from "./scope-banner";
import { SuggestedQuestions } from "./suggested-questions";
import { useConversation } from "./use-conversation";
import type { AskScope } from "./types";

export type AskScreenProps = {
  scope: AskScope;
  heading: string;
  /** A deep-linked question to ask immediately on landing here (S9.13's landing screen, `?q=`) — fires once, never re-fires on a re-render. */
  autoAskQuestion?: string;
};

/**
 * The shared ask screen for both `/books/:id/ask` and `/projects/:id/ask` —
 * everything about it is project-aware; the two routes differ only in the
 * `AskScope` they resolve (README's "build everything project-aware from the
 * first line").
 */
export const AskScreen = ({ scope, heading, autoAskQuestion }: AskScreenProps) => {
  // Hooks.
  const { turns, isActive, ask, respondToInterrupt } = useConversation(scope);

  // Refs.
  const hasAutoAskedRef = useRef(false);

  // useEffects.
  useEffect(() => {
    if (autoAskQuestion && !hasAutoAskedRef.current && turns.length === 0) {
      hasAutoAskedRef.current = true;
      ask(autoAskQuestion);
    }
  }, [autoAskQuestion, ask, turns.length]);

  return (
    <Stack gap="6">
      <Stack gap="2">
        <Heading as="h2" textStyle="heading">
          {heading}
        </Heading>
        <Text textStyle="body" color="fg.muted" maxW="measure">
          Plain-English questions, answered from the character graph and the
          text — every claim clicks through to the page that proves it.
        </Text>
      </Stack>

      <ScopeBanner scope={scope} />

      {turns.length === 0 ? (
        <SuggestedQuestions projectId={scope.projectId} onAsk={ask} />
      ) : (
        <ConversationThread turns={turns} onRespondToInterrupt={respondToInterrupt} />
      )}

      <InferenceModeNote />
      <AskComposer onAsk={ask} disabled={isActive} />
    </Stack>
  );
};

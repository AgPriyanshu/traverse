import { Button, HStack, Input, Stack, Text } from "@chakra-ui/react";
import { useState } from "react";
import type { FormEvent } from "react";

export type InterruptCardProps = {
  question: string;
  /** Selectable candidates (usually character names) — the common case needs no typing at all. */
  options?: readonly string[];
  onSelectOption: (option: string) => void;
  /** Omitted when the interrupt is options-only — S6.12's router path always offers this too. */
  onSubmitText?: (text: string) => void;
  isBusy?: boolean;
};

/**
 * A paused stream asking the person a question before it continues — the
 * router's ambiguous-query interrupt (S6.12) first, then Sprint 7's review
 * queue reuses this unchanged for a human-in-the-loop resolution. Kept
 * generic on purpose: no `QueryEvent` or `ReviewTask` import here.
 */
export const InterruptCard = ({
  question,
  options = [],
  onSelectOption,
  onSubmitText,
  isBusy = false,
}: InterruptCardProps) => {
  // States.
  const [freeText, setFreeText] = useState("");

  // Handlers.
  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = freeText.trim();
    if (trimmed === "" || !onSubmitText) { return; }
    onSubmitText(trimmed);
    setFreeText("");
  };

  return (
    <Stack
      gap="3"
      role="group"
      aria-label="Clarifying question"
      borderWidth="1px"
      borderColor="border.control"
      borderRadius="lg"
      bg="bg.sunken"
      padding="4"
    >
      <Text textStyle="body" fontWeight="600" color="fg">
        {question}
      </Text>

      {options.length > 0 ? (
        <HStack gap="2" wrap="wrap">
          {options.map((option) => (
            <Button
              key={option}
              size="sm"
              variant="outline"
              borderColor="border.control"
              color="fg"
              borderRadius="md"
              disabled={isBusy}
              onClick={() => { onSelectOption(option); }}
            >
              {option}
            </Button>
          ))}
        </HStack>
      ) : null}

      {onSubmitText ? (
        <form onSubmit={handleSubmit}>
          <HStack gap="2">
            <Input
              value={freeText}
              onChange={(event) => { setFreeText(event.target.value); }}
              placeholder="Or type your answer"
              aria-label="Answer the clarifying question"
              size="sm"
              flex="1"
              minW="0"
              borderColor="border.control"
              borderRadius="md"
              bg="bg.surface"
              disabled={isBusy}
            />
            <Button
              type="submit"
              size="sm"
              variant="solid"
              bg="accent.solid"
              color="accent.contrast"
              borderRadius="md"
              disabled={isBusy || freeText.trim() === ""}
            >
              Answer
            </Button>
          </HStack>
        </form>
      ) : null}
    </Stack>
  );
};

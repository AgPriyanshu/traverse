import { Button, HStack, Textarea } from "@chakra-ui/react";
import { useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";

export type AskComposerProps = {
  onAsk: (question: string) => void;
  disabled?: boolean;
};

export const AskComposer = ({ onAsk, disabled = false }: AskComposerProps) => {
  // States.
  const [value, setValue] = useState("");

  // Handlers.
  const submit = () => {
    const trimmed = value.trim();
    if (trimmed === "" || disabled) { return; }
    onAsk(trimmed);
    setValue("");
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <HStack gap="2" align="flex-start">
        <Textarea
          value={value}
          onChange={(event) => { setValue(event.target.value); }}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question about this book…"
          aria-label="Ask a question"
          rows={1}
          resize="none"
          flex="1"
          minW="0"
          borderColor="border.control"
          borderRadius="md"
          bg="bg.surface"
          disabled={disabled}
        />
        <Button
          type="submit"
          variant="solid"
          bg="accent.solid"
          color="accent.contrast"
          borderRadius="md"
          disabled={disabled || value.trim() === ""}
        >
          Ask
        </Button>
      </HStack>
    </form>
  );
};

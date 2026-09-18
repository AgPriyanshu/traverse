import { Circle, HStack, Span } from "@chakra-ui/react";
import type { StatusTone } from "./status-tone";
import { TONE_COLOR } from "./status-tone";

export type StatusDotProps = {
  tone: StatusTone;
  label: string;
  /** Hide the word when the row already names the thing being described. */
  labelHidden?: boolean;
};

/**
 * A dot and a word — never a bordered pill (design/DESIGN.md §2). The word is
 * what makes it legible without colour; the dot is what makes it scannable.
 */
export const StatusDot = ({
  tone,
  label,
  labelHidden = false,
}: StatusDotProps) => {
  return (
    <HStack gap="1.5" minW="0">
      <Circle size="1.5" bg={TONE_COLOR[tone]} flexShrink="0" aria-hidden="true" />
      <Span textStyle="small" color="fg.muted" truncate srOnly={labelHidden}>
        {label}
      </Span>
    </HStack>
  );
};

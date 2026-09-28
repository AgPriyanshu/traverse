import { HStack, Slider, Stack, Text } from "@chakra-ui/react";

export type ReadingPositionSliderProps = {
  index: number;
  maxIndex: number;
  label: string;
  isLimited: boolean;
  onChange: (index: number) => void;
  /** Disabled while the books whose chapters make up the scale are still loading. */
  disabled?: boolean;
};

/**
 * The persistent spoiler gate (F4.5, S8.6): "I've read up to chapter ___."
 * One step per chapter across every book in the project, laid end to end
 * (`buildPositionSteps`); the rightmost step is "caught up" — no limit at
 * all, the default, because most readers arrive having finished the book.
 *
 * This is a real server-side re-fetch on every surface that reads it (graph,
 * characters, ask), never a client-side visual filter — see the gotcha in
 * `web-app.md` about why the two must not be merged.
 */
export const ReadingPositionSlider = ({
  index,
  maxIndex,
  label,
  isLimited,
  onChange,
  disabled = false,
}: ReadingPositionSliderProps) => {
  return (
    <HStack
      as="fieldset"
      gap="4"
      wrap="wrap"
      align="center"
      borderWidth="1px"
      borderColor={isLimited ? "accent.solid" : "border"}
      borderRadius="md"
      bg={isLimited ? "accent.subtle" : "bg.sunken"}
      paddingInline="3"
      paddingBlock="2"
      data-testid="reading-position-slider"
    >
      <Text as="legend" textStyle="small" color="fg.muted" fontWeight="600" flexShrink="0">
        I&apos;ve read up to
      </Text>

      <Slider.Root
        minW="12rem"
        maxW="20rem"
        flex="1"
        min={0}
        max={maxIndex}
        step={1}
        value={[index]}
        disabled={disabled || maxIndex === 0}
        onValueChange={(details) => { onChange(details.value[0] ?? maxIndex); }}
        aria-label={["Reading position — chapter reached"]}
      >
        <Slider.Control>
          <Slider.Track>
            <Slider.Range />
          </Slider.Track>
          <Slider.Thumb index={0}>
            <Slider.HiddenInput />
          </Slider.Thumb>
        </Slider.Control>
      </Slider.Root>

      <Stack gap="0" flexShrink="0">
        <Text
          textStyle="small"
          color={isLimited ? "accent.fg" : "fg.subtle"}
          fontWeight={isLimited ? "600" : "400"}
          aria-live="polite"
        >
          {label}
        </Text>
        <Text textStyle="small" color="fg.subtle">
          Nothing past this point renders — graph, characters, or answers.
        </Text>
      </Stack>
    </HStack>
  );
};

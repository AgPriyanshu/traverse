import { Box, Button, Heading, Stack, Text } from "@chakra-ui/react";
import { ApiError, describeError, isApiError, titleForError } from "@/lib/api";

export type ErrorStateProps = {
  error: unknown;
  onRetry?: () => void;
  /** Overrides the derived heading when the screen knows better. */
  title?: string;
};

/**
 * The real message, the real status code, and a way out. A 501 from a frozen
 * endpoint is a state this product has on purpose, so it reads as "not built
 * yet" rather than as a crash.
 */
export const ErrorState = ({ error, onRetry, title }: ErrorStateProps) => {
  // Variables.
  const heading = title ?? titleForError(error);
  const message = describeError(error);
  const status = isApiError(error) ? (error as ApiError).status : undefined;
  const isExpected = isApiError(error) && error.isNotImplemented;

  return (
    <Box
      role="alert"
      borderWidth="1px"
      borderColor={isExpected ? "border" : "status.err"}
      borderRadius="lg"
      bg="bg.surface"
      padding="6"
    >
      <Stack gap="3" maxW="measure">
        <Stack gap="1">
          <Heading
            as="h2"
            textStyle="subheading"
            color={isExpected ? "fg" : "status.err"}
          >
            {heading}
          </Heading>
          {status !== undefined ? (
            <Text textStyle="data" color="fg.subtle">
              HTTP {status}
            </Text>
          ) : null}
        </Stack>

        <Text textStyle="body" color="fg.muted">
          {message}
        </Text>

        {onRetry ? (
          <Box>
            <Button
              size="sm"
              variant="outline"
              borderColor="border.control"
              color="fg"
              borderRadius="md"
              onClick={onRetry}
            >
              Try again
            </Button>
          </Box>
        ) : null}
      </Stack>
    </Box>
  );
};

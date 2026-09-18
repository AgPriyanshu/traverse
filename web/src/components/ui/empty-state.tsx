import { Box, Heading, Stack, Text } from "@chakra-ui/react";
import type { ReactNode } from "react";

export type EmptyStateProps = {
  title: string;
  description?: string;
  action?: ReactNode;
  /** Shown above the heading — a quiet mark, not an illustration. */
  eyebrow?: string;
};

/**
 * An empty shelf, not a blank page: it says what is missing and offers the one
 * action that fixes it.
 */
export const EmptyState = ({
  title,
  description,
  action,
  eyebrow,
}: EmptyStateProps) => {
  return (
    <Box
      borderWidth="1px"
      borderColor="border"
      borderRadius="lg"
      bg="bg.surface"
      paddingBlock="12"
      paddingInline="6"
    >
      <Stack gap="3" maxW="measure" marginInline="auto" textAlign="center">
        {eyebrow ? (
          <Text textStyle="data" color="fg.subtle" textTransform="lowercase">
            {eyebrow}
          </Text>
        ) : null}
        <Heading as="h2" textStyle="heading" color="fg">
          {title}
        </Heading>
        {description ? (
          <Text textStyle="body" color="fg.muted">
            {description}
          </Text>
        ) : null}
        {action ? <Box paddingBlockStart="3">{action}</Box> : null}
      </Stack>
    </Box>
  );
};

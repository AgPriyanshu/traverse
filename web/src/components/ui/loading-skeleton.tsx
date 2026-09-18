import { Box, SimpleGrid, Skeleton, Stack } from "@chakra-ui/react";

export type LoadingSkeletonProps = {
  variant?: "text" | "cards" | "rows";
  /** Lines, cards or rows to draw. */
  count?: number;
  label?: string;
};

/**
 * A placeholder shaped like the content it replaces, so the page does not
 * relayout when data lands.
 */
export const LoadingSkeleton = ({
  variant = "text",
  count = 3,
  label = "Loading",
}: LoadingSkeletonProps) => {
  // Constants.
  const items = Array.from({ length: count }, (_, index) => index);

  if (variant === "cards") {
    return (
      <SimpleGrid
        columns={{ base: 1, sm: 2, lg: 3 }}
        gap="4"
        role="status"
        aria-label={label}
      >
        {items.map((index) => (
          <Stack
            key={index}
            gap="3"
            borderWidth="1px"
            borderColor="border"
            borderRadius="lg"
            bg="bg.surface"
            padding="5"
          >
            <Skeleton height="5" width="70%" borderRadius="sm" />
            <Skeleton height="3.5" width="45%" borderRadius="sm" />
            <Skeleton height="3.5" width="60%" borderRadius="sm" />
          </Stack>
        ))}
      </SimpleGrid>
    );
  }

  if (variant === "rows") {
    return (
      <Stack gap="2" role="status" aria-label={label}>
        {items.map((index) => (
          <Skeleton key={index} height="10" borderRadius="md" />
        ))}
      </Stack>
    );
  }

  return (
    <Stack gap="2" maxW="measure" role="status" aria-label={label}>
      {items.map((index) => (
        <Box key={index}>
          <Skeleton
            height="3.5"
            width={index === items.length - 1 ? "55%" : "100%"}
            borderRadius="sm"
          />
        </Box>
      ))}
    </Stack>
  );
};

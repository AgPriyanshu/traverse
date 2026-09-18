import { Box, Heading, Stack, Text } from "@chakra-ui/react";
import { useLocation } from "react-router";

export type NotYetBuiltProps = {
  screen: string;
  sprint: number;
  note?: string;
};

/**
 * The placeholder for a route that is declared but not implemented. It names
 * the sprint the screen lands in, because "coming soon" tells a reviewer
 * nothing and tells the next agent less.
 */
export const NotYetBuilt = ({ screen, sprint, note }: NotYetBuiltProps) => {
  // Hooks.
  const location = useLocation();

  return (
    <Box
      borderWidth="1px"
      borderColor="border"
      borderStyle="dashed"
      borderRadius="lg"
      bg="bg.sunken"
      padding="8"
    >
      <Stack gap="3" maxW="measure">
        <Text textStyle="data" color="fg.subtle">
          sprint {sprint}
        </Text>
        <Heading as="h2" textStyle="heading">
          {screen} is not built yet
        </Heading>
        <Text textStyle="body" color="fg.muted">
          {note ??
            `The route is registered and the API contract is frozen, so this screen is a one-file swap when sprint ${sprint} lands.`}
        </Text>
        <Text textStyle="data" color="fg.subtle">
          {location.pathname}
        </Text>
      </Stack>
    </Box>
  );
};

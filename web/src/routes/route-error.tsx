import { Button, Stack } from "@chakra-ui/react";
import { Link as RouterLink, isRouteErrorResponse, useRouteError } from "react-router";
import { ErrorState } from "@/components/ui";

/**
 * The last surface before a white screen. It renders inside the shell so a
 * failed route still leaves the reader somewhere to go.
 */
export const RouteError = () => {
  // Hooks.
  const error = useRouteError();

  // Variables.
  const message = isRouteErrorResponse(error)
    ? new Error(`${error.status} ${error.statusText}`)
    : error;

  return (
    <Stack gap="6" padding={{ base: "4", md: "7" }} maxW="shell" marginInline="auto">
      <ErrorState error={message} title="This screen failed to load" />
      <div>
        <Button asChild size="sm" variant="outline" borderColor="border.control" borderRadius="md">
          <RouterLink to="/books">Back to the library</RouterLink>
        </Button>
      </div>
    </Stack>
  );
};

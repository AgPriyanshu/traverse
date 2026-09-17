import { Button, Stack } from "@chakra-ui/react";
import { Link as RouterLink } from "react-router";
import { EmptyState } from "@/components/ui";

export const NotFound = () => {
  return (
    <Stack gap="6">
      <EmptyState
        eyebrow="404"
        title="There is no page here"
        description="The link may be from an older version of Traverse, or the book it pointed at has been removed."
        action={
          <Button asChild size="sm" variant="outline" borderColor="border.control" borderRadius="md">
            <RouterLink to="/books">Back to the library</RouterLink>
          </Button>
        }
      />
    </Stack>
  );
};

export default NotFound;

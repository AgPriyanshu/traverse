import { Box, Heading, Link, Stack, Text } from "@chakra-ui/react";
import { useParams } from "react-router";
import { ErrorState, LoadingSkeleton } from "@/components/ui";
import { useBookStatus } from "@/lib/api";
import { formatSecondsRemaining } from "@/lib/format";
import { StageStepper } from "./stage-stepper";

export const BookOverview = () => {
  // Hooks.
  const { bookId = "" } = useParams();

  // Apis.
  const status = useBookStatus(bookId);

  // Variables.
  const remaining = formatSecondsRemaining(
    status.data?.estimated_seconds_remaining,
  );

  return (
    <Stack gap="7" maxW="measure">
      <Stack gap="2">
        <Heading as="h2" textStyle="heading">
          Ingestion
        </Heading>
        <Text textStyle="body" color="fg.muted">
          Nine stages take a PDF to a cited graph. Each one records how long it
          took and what it failed on, so a long run never looks like a stuck one.
        </Text>
        {remaining ? (
          <Text textStyle="data" color="fg.subtle">
            {remaining}
          </Text>
        ) : null}
      </Stack>

      {status.isPending ? (
        <LoadingSkeleton variant="rows" count={4} label="Loading stages" />
      ) : null}

      {status.error ? (
        <ErrorState
          error={status.error}
          onRetry={() => void status.refetch()}
          title="No ingestion run reported yet"
        />
      ) : null}

      {!status.isPending ? (
        <Box>
          <StageStepper stages={status.data?.stages} />
        </Box>
      ) : null}

      {status.data?.trace_url ? (
        <Box>
          <Link
            href={status.data.trace_url}
            target="_blank"
            rel="noreferrer"
            textStyle="small"
            color="accent.fg"
          >
            Open the trace
          </Link>
        </Box>
      ) : null}
    </Stack>
  );
};

export default BookOverview;

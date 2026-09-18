import { Box, Heading, Link, Stack, Text } from "@chakra-ui/react";
import { useState } from "react";
import { useParams } from "react-router";
import { ErrorState, LoadingSkeleton } from "@/components/ui";
import type { StageName } from "@/lib/api";
import { useBookStatus, useReprocessBook } from "@/lib/api";
import { formatSecondsRemaining } from "@/lib/format";
import { estimateSecondsRemaining } from "@/lib/ingestion-eta";
import { StageStepper } from "./stage-stepper";

export const BookOverview = () => {
  // States.
  const [retryingStage, setRetryingStage] = useState<StageName | undefined>(
    undefined,
  );

  // Hooks.
  const { bookId = "" } = useParams();

  // Apis.
  const status = useBookStatus(bookId);
  const reprocess = useReprocessBook(bookId);

  // Variables.
  // The backend does not populate this yet (nothing in this sprint computes
  // it) — fall back to a local estimate from this book's own stage durations
  // rather than showing nothing for the whole sprint.
  const remaining = formatSecondsRemaining(
    status.data?.estimated_seconds_remaining ??
      estimateSecondsRemaining(status.data?.stages),
  );

  // Handlers.
  const handleRetryStage = (stageName: StageName) => {
    setRetryingStage(stageName);
    reprocess.mutate(stageName, {
      onSettled: () => { setRetryingStage(undefined); },
    });
  };

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
          <StageStepper
            stages={status.data?.stages}
            onRetryStage={handleRetryStage}
            retryingStage={retryingStage}
          />
        </Box>
      ) : null}

      {reprocess.error ? (
        <ErrorState error={reprocess.error} title="The retry did not start" />
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

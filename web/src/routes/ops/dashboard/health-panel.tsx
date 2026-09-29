import { Heading, HStack, Link as ChakraLink, SimpleGrid, Stack, Text } from "@chakra-ui/react";
import { useMemo } from "react";
import { Link as RouterLink } from "react-router";
import { ErrorState, LoadingSkeleton, StatusDot } from "@/components/ui";
import {
  STAGE_LABELS,
  useBooks,
  useDeadLetter,
  usePipelineRuns,
  useReviewAlerts,
} from "@/lib/api";
import type { IngestionRun } from "@/lib/api";
import { formatCount } from "@/lib/format";

const RUN_LIMIT = 10;

const runStatus = (run: IngestionRun): "ok" | "err" | "busy" => {
  if (run.stages.some((stage) => stage.state === "failed")) { return "err"; }
  if (run.stages.some((stage) => stage.state === "running" || stage.state === "pending")) { return "busy"; }
  return "ok";
};

const StatTile = ({ label, value, tone }: { label: string; value: string; tone?: "ok" | "err" }) => (
  <Stack gap="0.5" borderWidth="1px" borderColor="border" borderRadius="lg" bg="bg.surface" padding="4">
    <Text textStyle="small" color="fg.muted">{label}</Text>
    <Text textStyle="heading" color={tone === "err" ? "status.err" : "fg"} fontFamily="mono">
      {value}
    </Text>
  </Stack>
);

/**
 * F7.4 — pipeline health: run history, failure rates, dead-letter, trace
 * links, plus the review queue's own alert set (S7.11's `GET
 * /ops/review-alerts`) folded in — a stuck review queue is as much a
 * production-health signal as a failed ingestion stage.
 */
export const HealthPanel = () => {
  // Apis.
  const runs = usePipelineRuns({ limit: RUN_LIMIT });
  const deadLetter = useDeadLetter();
  const reviewAlerts = useReviewAlerts();
  const books = useBooks();

  // useMemos.
  const bookTitleById = useMemo(() => {
    return new Map((books.data ?? []).map((book) => [book.id, book.title]));
  }, [books.data]);

  const failedCount = (runs.data ?? []).filter((run) => runStatus(run) === "err").length;

  return (
    <Stack as="section" gap="4" borderWidth="1px" borderColor="border" borderRadius="lg" bg="bg.surface" padding="5">
      <Heading as="h2" textStyle="subheading">Pipeline health</Heading>

      <SimpleGrid columns={{ base: 1, sm: 3 }} gap="3">
        <StatTile
          label={`Recent runs (last ${RUN_LIMIT})`}
          value={formatCount(runs.data?.length ?? 0, "run")}
        />
        <StatTile
          label="Failing now"
          value={String(failedCount)}
          tone={failedCount > 0 ? "err" : undefined}
        />
        <StatTile
          label="Dead-letter"
          value={formatCount(deadLetter.data?.length ?? 0, "book")}
          tone={(deadLetter.data?.length ?? 0) > 0 ? "err" : undefined}
        />
      </SimpleGrid>

      <Stack gap="2">
        <Text textStyle="small" fontWeight="600" color="fg">Recent runs</Text>
        {runs.isPending ? <LoadingSkeleton variant="rows" count={4} label="Loading pipeline runs" /> : null}
        {!runs.isPending && runs.error ? <ErrorState error={runs.error} onRetry={() => { void runs.refetch(); }} /> : null}
        {!runs.isPending && !runs.error && (runs.data?.length ?? 0) === 0 ? (
          <Text textStyle="body" color="fg.muted">No ingestion runs recorded yet.</Text>
        ) : null}
        {!runs.isPending && !runs.error ? (
          <Stack gap="2" as="ul" role="list">
            {(runs.data ?? []).map((run) => {
              const failedStage = run.stages.find((stage) => stage.state === "failed");
              const status = runStatus(run);
              return (
                <HStack
                  key={run.run_id}
                  as="li"
                  justify="space-between"
                  gap="3"
                  borderWidth="1px"
                  borderColor="border"
                  borderRadius="md"
                  padding="2.5"
                  wrap="wrap"
                >
                  <Stack gap="0.5" minW="0">
                    <ChakraLink asChild textStyle="small" fontWeight="600" color="fg">
                      <RouterLink to={`/books/${run.book_id}`}>
                        {bookTitleById.get(run.book_id) ?? run.book_id}
                      </RouterLink>
                    </ChakraLink>
                    {failedStage ? (
                      <Text textStyle="small" color="status.err">
                        {STAGE_LABELS[failedStage.stage] ?? failedStage.stage}
                        {failedStage.error ? `: ${failedStage.error}` : ""}
                      </Text>
                    ) : null}
                  </Stack>
                  <HStack gap="3" flexShrink="0">
                    <StatusDot
                      tone={status}
                      label={status === "err" ? "Failed" : status === "busy" ? "In progress" : "Succeeded"}
                    />
                    {run.trace_url ? (
                      <ChakraLink href={run.trace_url} target="_blank" rel="noreferrer" textStyle="small">
                        Trace
                      </ChakraLink>
                    ) : null}
                  </HStack>
                </HStack>
              );
            })}
          </Stack>
        ) : null}
      </Stack>

      <Stack gap="2">
        <Text textStyle="small" fontWeight="600" color="fg">Review queue alerts</Text>
        {reviewAlerts.isPending ? <LoadingSkeleton variant="rows" count={2} label="Loading review alerts" /> : null}
        {!reviewAlerts.isPending && reviewAlerts.error ? (
          <ErrorState error={reviewAlerts.error} onRetry={() => { void reviewAlerts.refetch(); }} />
        ) : null}
        {!reviewAlerts.isPending && !reviewAlerts.error && reviewAlerts.data ? (
          reviewAlerts.data.has_alerts ? (
            <Stack gap="1.5">
              {reviewAlerts.data.queue_depth_breached ? (
                <Text textStyle="small" color="status.err">
                  Queue depth {reviewAlerts.data.queue_depth_total} exceeds the {reviewAlerts.data.queue_depth_threshold}-task threshold.
                </Text>
              ) : null}
              {(reviewAlerts.data.stale_tasks?.length ?? 0) > 0 ? (
                <Text textStyle="small" color="status.warn">
                  {formatCount(reviewAlerts.data.stale_tasks?.length, "task")} open past {reviewAlerts.data.stale_task_threshold_hours}h.
                </Text>
              ) : null}
              {(reviewAlerts.data.orphaned_threads?.length ?? 0) > 0 ? (
                <Text textStyle="small" color="status.err">
                  {formatCount(reviewAlerts.data.orphaned_threads?.length, "orphaned graph thread")} paused with no open review task.
                </Text>
              ) : null}
            </Stack>
          ) : (
            <StatusDot tone="ok" label={`Queue depth ${reviewAlerts.data.queue_depth_total} — no alerts`} />
          )
        ) : null}
      </Stack>

      {!deadLetter.isPending && !deadLetter.error && (deadLetter.data?.length ?? 0) > 0 ? (
        <Stack gap="2">
          <Text textStyle="small" fontWeight="600" color="fg">Dead-letter</Text>
          <Stack gap="1.5" as="ul" role="list">
            {(deadLetter.data ?? []).map((entry) => (
              <HStack key={`${entry.book_id}-${entry.stage}`} as="li" justify="space-between" gap="3" wrap="wrap">
                <Text textStyle="small" color="fg">
                  {entry.book_title} — {STAGE_LABELS[entry.stage as keyof typeof STAGE_LABELS] ?? entry.stage}
                  {entry.error_message ? `: ${entry.error_message}` : ""}
                </Text>
                <HStack gap="2" flexShrink="0">
                  <Text textStyle="data" color="fg.muted">{formatCount(entry.attempts, "attempt")}</Text>
                  {entry.trace_url ? (
                    <ChakraLink href={entry.trace_url} target="_blank" rel="noreferrer" textStyle="small">Trace</ChakraLink>
                  ) : null}
                </HStack>
              </HStack>
            ))}
          </Stack>
        </Stack>
      ) : null}
    </Stack>
  );
};

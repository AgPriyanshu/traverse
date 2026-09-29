import { Box, Field, Heading, HStack, NativeSelect, SimpleGrid, Stack, Text } from "@chakra-ui/react";
import { useMemo, useState } from "react";
import { ErrorState, LoadingSkeleton, StatusDot } from "@/components/ui";
import { useProjects, useQueryLatency } from "@/lib/api";
import { formatCount, formatDuration } from "@/lib/format";
import { PercentileBarChart } from "./percentile-bar-chart";

const STAGE_LABEL: Record<string, string> = {
  retrieval: "Retrieval",
  rerank: "Rerank",
  generation: "Generation",
  grounding: "Grounding",
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
 * F7.2 — latency by stage (p50/p95/p99), TTFT, against the NFR-perf budget.
 * Live off `GET /ops/query-latency`, project-scoped (be2's `QueryLog` rows,
 * S6.15) — there is no cross-project aggregate route, so this panel picks
 * one project rather than fabricating a sum across incomparable corpora.
 *
 * GPU/KV occupancy and queue depth (also named in the S9.2 brief) have no
 * contract field yet — do1's S9.2 telemetry, not landed in this worktree as
 * of this commit — so that half of the panel is a clearly labelled
 * placeholder rather than a silently invented number.
 */
export const PerformancePanel = () => {
  // States.
  const [projectId, setProjectId] = useState<string | undefined>(undefined);

  // Apis.
  const projects = useProjects();
  const activeProjectId = projectId ?? projects.data?.[0]?.id;
  const latency = useQueryLatency(activeProjectId);

  // useMemos.
  const stages = useMemo(() => {
    if (!latency.data) { return []; }
    return Object.entries(latency.data.per_stage_ms).map(([stage, percentiles]) => ({
      label: STAGE_LABEL[stage] ?? stage,
      percentiles,
    }));
  }, [latency.data]);

  return (
    <Stack as="section" gap="3" borderWidth="1px" borderColor="border" borderRadius="lg" bg="bg.surface" padding="5">
      <HStack justify="space-between" wrap="wrap" gap="3">
        <Heading as="h2" textStyle="subheading">Performance</Heading>
        {(projects.data?.length ?? 0) > 1 ? (
          <Field.Root maxW="14rem">
            <NativeSelect.Root size="sm">
              <NativeSelect.Field
                value={activeProjectId ?? ""}
                borderColor="border.control"
                borderRadius="md"
                bg="bg.surface"
                aria-label="Project"
                onChange={(event) => { setProjectId(event.target.value); }}
              >
                {projects.data?.map((project) => (
                  <option key={project.id} value={project.id}>{project.name}</option>
                ))}
              </NativeSelect.Field>
              <NativeSelect.Indicator />
            </NativeSelect.Root>
          </Field.Root>
        ) : null}
      </HStack>

      {projects.isPending ? <LoadingSkeleton variant="rows" count={3} label="Loading projects" /> : null}
      {!projects.isPending && projects.error ? <ErrorState error={projects.error} /> : null}

      {!projects.isPending && !projects.error && !activeProjectId ? (
        <Text textStyle="body" color="fg.muted">No project to measure yet — upload a book to get latency samples.</Text>
      ) : null}

      {activeProjectId && latency.isPending ? (
        <LoadingSkeleton variant="rows" count={3} label="Loading query latency" />
      ) : null}
      {activeProjectId && !latency.isPending && latency.error ? (
        <ErrorState error={latency.error} onRetry={() => { void latency.refetch(); }} />
      ) : null}

      {activeProjectId && !latency.isPending && !latency.error && latency.data ? (
        <Stack gap="5">
          <SimpleGrid columns={{ base: 1, sm: 3 }} gap="3">
            <StatTile label="Samples" value={formatCount(latency.data.sample_count, "query", "queries")} />
            <StatTile
              label={`Total, p95 (budget ${latency.data.p95_budget_ms} ms)`}
              value={formatDuration(latency.data.total_ms.p95)}
              tone={latency.data.p95_within_budget === false ? "err" : undefined}
            />
            <StatTile
              label={`Time to first token, p95 (budget ${latency.data.ttft_budget_ms} ms)`}
              value={formatDuration(latency.data.ttft_ms.p95)}
              tone={latency.data.ttft_p95_within_budget === false ? "err" : undefined}
            />
          </SimpleGrid>

          <HStack gap="4" wrap="wrap">
            <StatusDot
              tone={
                latency.data.p95_within_budget === false
                  ? "err"
                  : latency.data.p95_within_budget === null
                    ? "idle"
                    : "ok"
              }
              label={
                latency.data.p95_within_budget === false
                  ? "Total latency over budget"
                  : latency.data.p95_within_budget === null
                    ? "Total latency budget: not enough samples yet"
                    : "Total latency within budget"
              }
            />
            <StatusDot
              tone={
                latency.data.ttft_p95_within_budget === false
                  ? "err"
                  : latency.data.ttft_p95_within_budget === null
                    ? "idle"
                    : "ok"
              }
              label={
                latency.data.ttft_p95_within_budget === false
                  ? "Time to first token over budget"
                  : latency.data.ttft_p95_within_budget === null
                    ? "TTFT budget: not enough samples yet"
                    : "Time to first token within budget"
              }
            />
          </HStack>

          {latency.data.violations.length > 0 ? (
            <Stack gap="1" as="ul">
              {latency.data.violations.map((violation) => (
                <Text as="li" key={violation} textStyle="small" color="status.err">{violation}</Text>
              ))}
            </Stack>
          ) : null}

          <Stack gap="2">
            <Text textStyle="small" fontWeight="600" color="fg">Latency by stage</Text>
            <PercentileBarChart stages={stages} />
          </Stack>
        </Stack>
      ) : null}

      <Box borderWidth="1px" borderColor="border" borderRadius="md" bg="bg.sunken" padding="3">
        <Text textStyle="small" color="fg.muted">
          Throughput and GPU/KV-cache occupancy over time are do1&apos;s S9.2
          telemetry and have no live route in this worktree yet — this panel
          intentionally omits a fabricated chart for them rather than
          inventing numbers. Swap point: a `useThroughput`/`useGpuOccupancy`
          hook here once `api/ops/**` exposes them.
        </Text>
      </Box>
    </Stack>
  );
};

import { Heading, SimpleGrid, Stack, Text } from "@chakra-ui/react";
import { ErrorState, LoadingSkeleton } from "@/components/ui";
import { useMetrics } from "@/lib/api";
import { formatCurrency, formatPercent } from "@/lib/format";
import { StackedCostBar } from "./stacked-cost-bar";

const STAGE_LABEL: Record<string, string> = {
  chapter_classify: "Chapter classification",
  character_extract: "Character extraction (pass 1)",
  relation_extract: "Relation extraction (pass 2)",
  adjudicate: "Adjudication",
  answer: "Answering",
  judge: "Answer judging",
};

const StatTile = ({ label, value }: { label: string; value: string }) => (
  <Stack gap="0.5" borderWidth="1px" borderColor="border" borderRadius="lg" bg="bg.surface" padding="4">
    <Text textStyle="small" color="fg.muted">{label}</Text>
    <Text textStyle="heading" color="fg" fontFamily="mono">{value}</Text>
  </Stack>
);

const CostPanelContent = ({ data }: { data: NonNullable<ReturnType<typeof useMetrics>["data"]> }) => {
  const stages = data.stages ?? [];
  const segments = stages.map((stage) => ({
    label: STAGE_LABEL[stage.stage] ?? stage.stage,
    value: stage.cost_usd,
  }));

  return (
    <Stack gap="5">
      <SimpleGrid columns={{ base: 1, sm: 3 }} gap="3">
        <StatTile label="Total spend, all books" value={formatCurrency(data.total_cost_usd)} />
        <StatTile
          label="Prefix-cache hit rate"
          value={data.prefix_cache_hit_rate === null || data.prefix_cache_hit_rate === undefined ? "n/a (API inference)" : formatPercent(data.prefix_cache_hit_rate)}
        />
        <StatTile label="Stages reporting" value={String(stages.length)} />
      </SimpleGrid>

      <Stack gap="2">
        <Text textStyle="small" fontWeight="600" color="fg">Cost by stage</Text>
        <StackedCostBar
          segments={segments}
          total={data.total_cost_usd}
          ariaLabel={`Total cost ${formatCurrency(data.total_cost_usd)}, broken down by pipeline stage`}
        />
      </Stack>
    </Stack>
  );
};

/**
 * F7.1 — cost telemetry by stage, rolling spend. Live off `GET /ops/metrics`
 * (do1, built since S2.17) with no `book_id`, which sums every run ever
 * recorded rather than one book's latest.
 */
export const CostPanel = () => {
  const metrics = useMetrics();

  return (
    <Stack as="section" gap="3" borderWidth="1px" borderColor="border" borderRadius="lg" bg="bg.surface" padding="5">
      <Heading as="h2" textStyle="subheading">Cost</Heading>
      {metrics.isPending ? <LoadingSkeleton variant="rows" count={3} label="Loading cost telemetry" /> : null}
      {!metrics.isPending && metrics.error ? (
        <ErrorState error={metrics.error} onRetry={() => { void metrics.refetch(); }} />
      ) : null}
      {!metrics.isPending && !metrics.error && metrics.data ? (
        <CostPanelContent data={metrics.data} />
      ) : null}
    </Stack>
  );
};

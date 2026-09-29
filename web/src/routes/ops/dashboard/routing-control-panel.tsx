import { Badge, Button, Field, Heading, HStack, NativeSelect, SimpleGrid, Stack, Text } from "@chakra-ui/react";
import { useMemo, useState } from "react";
import { toaster } from "@/components/ui";
import { isApiError, useEvalRunLatest, useRoutingPolicy, useSetRoutingPolicy } from "@/lib/api";
import { formatCurrency, formatPointsDelta } from "@/lib/format";
import { DEFAULT_POLICY, LLM_PURPOSES, MODEL_CHOICES, QUERY_PURPOSES, asPolicyRecord } from "@/lib/inference-mode";
import {
  COST_TREND,
  FALLBACK_MODEL_AXIS_RESULTS,
  costPerQueryFor,
} from "./fixtures";
import type { LlmPurpose, ModelChoice } from "./types";
import { findModelAxisResult } from "./types";

const MODEL_LABEL: Record<ModelChoice, string> = {
  local: "Local (Qwen3-8B-AWQ)",
  frontier: "Frontier API",
  routed: "Routed (local, frontier fallback)",
};

const PURPOSE_LABEL: Record<LlmPurpose, string> = {
  chapter_classify: "Chapter classification",
  character_extract: "Character extraction",
  relation_extract: "Relation extraction",
  adjudicate: "Adjudication",
  answer: "Answering a query",
  judge: "Judging an answer (eval only)",
};

/**
 * F7.3, the "closing-argument screen." Flipping any purpose's model choice
 * must move cost-per-query and the eval accuracy delta *at once*, side by
 * side — a settings form with a save button throws away the whole point
 * (frontend-1.md).
 *
 * Two honest seams, both documented rather than papered over:
 * 1. `GET/PUT /ops/routing-policy` are `not_implemented` stubs (S9.6, be2,
 *    not landed in this worktree as of this commit) — this panel opens on
 *    `DEFAULT_POLICY` and edits it entirely client-side; "Apply" attempts
 *    the real `PUT` and reports whether it actually took.
 * 2. Cost-per-query is computed from `fixtures.ts`'s labelled unit-cost
 *    table (no live per-call cost meter exists — that's `CostBreakdown`'s
 *    own gap, `./types.ts`). Accuracy is real when a gold-set ablation run
 *    exists in this worktree's database (`GET /ops/eval-runs/latest`,
 *    built since S8.8) and falls back to a labelled fixture only when none
 *    does (`FALLBACK_MODEL_AXIS_RESULTS`) — see `./fixtures.ts`.
 */
export const RoutingControlPanel = () => {
  // Apis.
  const routingPolicy = useRoutingPolicy();
  const setRoutingPolicy = useSetRoutingPolicy();
  const evalRun = useEvalRunLatest();

  // States.
  const [policy, setPolicy] = useState<Record<LlmPurpose, ModelChoice>>(
    asPolicyRecord(DEFAULT_POLICY),
  );
  const [policyVersion, setPolicyVersion] = useState(DEFAULT_POLICY.version);
  // `null` until the first successful live fetch syncs local edit state to
  // it — a render-time reset (React's own documented pattern, matching
  // `chunk-inspector.tsx`/`page-viewer.tsx` elsewhere in this codebase), not
  // a `useEffect`, since `oxlint`'s `set-state-in-effect` flags the effect
  // version as risking a cascading extra render for no benefit here.
  const [syncedVersion, setSyncedVersion] = useState<number | null>(null);
  if (routingPolicy.data && routingPolicy.data.version !== syncedVersion) {
    setSyncedVersion(routingPolicy.data.version);
    setPolicy(asPolicyRecord(routingPolicy.data));
    setPolicyVersion(routingPolicy.data.version);
  }

  // useMemos.
  const liveResults = evalRun.data?.results ?? [];
  const modelAxisResults = liveResults.length > 0 ? liveResults : FALLBACK_MODEL_AXIS_RESULTS;
  const usingFallbackEval = liveResults.length === 0;

  const costPerQuery = useMemo(() => costPerQueryFor(policy), [policy]);
  const localCostPerQuery = useMemo(
    () => costPerQueryFor(asPolicyRecord(DEFAULT_POLICY)),
    [],
  );
  const costDeltaPct = localCostPerQuery > 0
    ? ((costPerQuery - localCostPerQuery) / localCostPerQuery) * 100
    : 0;

  const answerAccuracyResult = findModelAxisResult(modelAxisResults, policy.answer);
  const localAccuracyResult = findModelAxisResult(modelAxisResults, "local");
  const accuracy = answerAccuracyResult?.metrics.accuracy ?? null;
  const localAccuracy = localAccuracyResult?.metrics.accuracy ?? null;
  const accuracyDelta = accuracy !== null && localAccuracy !== null ? accuracy - localAccuracy : null;

  // Handlers.
  const handleChange = (purpose: LlmPurpose, value: ModelChoice) => {
    setPolicy((previous) => ({ ...previous, [purpose]: value }));
  };

  const handleApply = () => {
    setRoutingPolicy.mutate(
      { version: policyVersion + 1, purposes: policy },
      {
        onSuccess: (result) => {
          setPolicyVersion(result.version);
          toaster.create({
            type: "success",
            title: "Routing policy applied",
            description: "The live routing engine is now serving this policy.",
          });
        },
        onError: (error) => {
          const isNotBuilt = isApiError(error) && error.isNotImplemented;
          toaster.create({
            type: isNotBuilt ? "info" : "error",
            title: isNotBuilt ? "Preview only" : "Could not apply the policy",
            description: isNotBuilt
              ? "The live routing engine (S9.6) hasn't landed yet — the numbers above are a live preview of this policy, not yet wired to real traffic."
              : "The API rejected the change. The preview above is unaffected.",
          });
        },
      },
    );
  };

  return (
    <Stack as="section" gap="5" borderWidth="1px" borderColor="accent.solid" borderRadius="lg" bg="bg.surface" padding="5">
      <Stack gap="1">
        <HStack justify="space-between" wrap="wrap" gap="2">
          <Heading as="h2" textStyle="subheading">Routing policy</Heading>
          {usingFallbackEval ? (
            <Badge variant="outline" size="sm">Accuracy: fixture — no ablation run recorded here yet</Badge>
          ) : (
            <Badge colorPalette="orange" size="sm">Accuracy: live eval run</Badge>
          )}
        </HStack>
        <Text textStyle="body" color="fg.muted" maxW="measure">
          Per-purpose model selection. Change any purpose below and both
          numbers move together — this is the trade a buyer is here to see.
        </Text>
      </Stack>

      <SimpleGrid columns={{ base: 1, md: 2 }} gap="4">
        {QUERY_PURPOSES.map((purpose) => (
          <Field.Root key={purpose}>
            <Field.Label textStyle="small" color="fg.muted">{PURPOSE_LABEL[purpose]}</Field.Label>
            <NativeSelect.Root size="sm">
              <NativeSelect.Field
                value={policy[purpose]}
                borderColor="border.control"
                borderRadius="md"
                bg="bg.surface"
                onChange={(event) => { handleChange(purpose, event.target.value as ModelChoice); }}
              >
                {MODEL_CHOICES.map((choice) => (
                  <option key={choice} value={choice}>{MODEL_LABEL[choice]}</option>
                ))}
              </NativeSelect.Field>
              <NativeSelect.Indicator />
            </NativeSelect.Root>
          </Field.Root>
        ))}
      </SimpleGrid>

      <details>
        <summary>
          <Text as="span" textStyle="small" color="fg.muted" cursor="pointer">
            Extraction pipeline purposes (don&apos;t affect a live query)
          </Text>
        </summary>
        <SimpleGrid columns={{ base: 1, md: 2 }} gap="4" marginTop="3">
          {LLM_PURPOSES.filter((purpose) => !QUERY_PURPOSES.includes(purpose)).map((purpose) => (
            <Field.Root key={purpose}>
              <Field.Label textStyle="small" color="fg.muted">{PURPOSE_LABEL[purpose]}</Field.Label>
              <NativeSelect.Root size="sm">
                <NativeSelect.Field
                  value={policy[purpose]}
                  borderColor="border.control"
                  borderRadius="md"
                  bg="bg.surface"
                  onChange={(event) => { handleChange(purpose, event.target.value as ModelChoice); }}
                >
                  {MODEL_CHOICES.map((choice) => (
                    <option key={choice} value={choice}>{MODEL_LABEL[choice]}</option>
                  ))}
                </NativeSelect.Field>
                <NativeSelect.Indicator />
              </NativeSelect.Root>
            </Field.Root>
          ))}
        </SimpleGrid>
      </details>

      <SimpleGrid columns={{ base: 1, sm: 2 }} gap="4">
        <Stack gap="1" borderWidth="1px" borderColor="border" borderRadius="lg" bg="bg.sunken" padding="4">
          <Text textStyle="small" color="fg.muted">Cost per query</Text>
          <Text textStyle="display" color="fg" fontFamily="mono">{formatCurrency(costPerQuery)}</Text>
          <Text
            textStyle="small"
            color={costDeltaPct <= 0 ? "status.ok" : "status.err"}
          >
            {costDeltaPct === 0 ? "same as fully local" : `${costDeltaPct > 0 ? "+" : ""}${costDeltaPct.toFixed(0)}% vs. fully local`}
          </Text>
        </Stack>

        <Stack gap="1" borderWidth="1px" borderColor="border" borderRadius="lg" bg="bg.sunken" padding="4">
          <Text textStyle="small" color="fg.muted">Answer accuracy</Text>
          <Text textStyle="display" color="fg" fontFamily="mono">
            {accuracy === null ? "—" : `${(accuracy * 100).toFixed(1)}%`}
          </Text>
          <Text
            textStyle="small"
            color={accuracyDelta !== null && accuracyDelta < 0 ? "status.err" : "status.ok"}
          >
            {accuracyDelta === null ? "no baseline yet" : `${formatPointsDelta(accuracyDelta)} vs. fully local`}
          </Text>
        </Stack>
      </SimpleGrid>

      <Stack gap="2">
        <Text textStyle="small" fontWeight="600" color="fg">Cost per query, last 7 days</Text>
        <CostTrend />
      </Stack>

      <HStack justify="flex-end">
        <Button
          size="sm"
          bg="accent.solid"
          color="accent.contrast"
          borderRadius="md"
          _hover={{ opacity: 0.9 }}
          onClick={handleApply}
          loading={setRoutingPolicy.isPending}
        >
          Apply to live traffic
        </Button>
      </HStack>
    </Stack>
  );
};

const CostTrend = () => {
  const values = COST_TREND.map((point) => point.total_cost_usd / Math.max(point.query_count, 1));
  const max = Math.max(...values);
  const width = 560;
  const height = 90;
  const padX = 6;
  const padY = 10;
  const stepX = (width - padX * 2) / (values.length - 1);
  const toY = (value: number) => height - padY - (value / max) * (height - padY * 2);
  const points = values.map((value, index) => `${padX + index * stepX},${toY(value)}`).join(" ");

  return (
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Cost per query over the last 7 days, with policy changes annotated"
    >
      <line x1={padX} y1={height - padY} x2={width - padX} y2={height - padY} stroke="var(--chakra-colors-border)" strokeWidth={1} />
      <polyline points={points} fill="none" stroke="var(--chakra-colors-accent-solid)" strokeWidth={2} />
      {COST_TREND.map((point, index) => (
        <g key={point.window_start}>
          <circle cx={padX + index * stepX} cy={toY(values[index] as number)} r={point.policy_change ? 5 : 3} fill="var(--chakra-colors-accent-solid)">
            <title>{`${new Date(point.window_start).toLocaleDateString()}: ${formatCurrency(values[index] as number)}/query${point.policy_change ? ` — ${point.policy_change}` : ""}`}</title>
          </circle>
          {point.policy_change ? (
            <text x={padX + index * stepX} y={12} textAnchor="middle" fontSize="9" fill="var(--chakra-colors-fg-muted)">
              ▲
            </text>
          ) : null}
        </g>
      ))}
    </svg>
  );
};

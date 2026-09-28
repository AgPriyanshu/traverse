import { HStack, Heading, Stack, Text } from "@chakra-ui/react";
import { useState } from "react";
import { formatAbsoluteTime, formatCount } from "@/lib/format";
import { AblationTable } from "./ablation-table";
import { CalibrationChart } from "./calibration-chart";
import { CALIBRATION, EVAL_RUNS, LATEST_RUN } from "./fixtures";
import { MetricDrawer } from "./metric-drawer";
import { MetricTrendChart } from "./metric-trend-chart";
import type { EvalResultOut } from "./types";

/**
 * The ablation matrix, live and drillable (F6.3, S8.7) — "a buyer who sees a
 * live, drillable ablation table understands immediately that the numbers
 * are real and not a README claim" (frontend-1.md).
 *
 * **Fixture data.** `do1`'s ablation runner (S8.8) has no live route yet as
 * of this screen, so `fixtures.ts` stands in with numbers matching the frozen
 * contract shapes exactly (`EvalRunOut`/`EvalResultOut`/`AblationConfig`/
 * `MetricSet`/`CalibrationModelOut`). Swapping in a real fetch only touches
 * this file's two imports from `./fixtures` — everything downstream
 * (`AblationTable`, `CalibrationChart`, `MetricTrendChart`, `MetricDrawer`)
 * already renders off the typed contract shape, not the fixture module.
 */
export const EvalsScreen = () => {
  // States.
  const [drillIn, setDrillIn] = useState<EvalResultOut | null>(null);

  // Variables.
  const run = LATEST_RUN;

  return (
    <Stack gap="8">
      <Stack gap="2">
        <Heading as="h2" textStyle="heading">
          Evaluation results
        </Heading>
        <Text textStyle="body" color="fg.muted" maxW="measure">
          Every cell holds one axis value against the recommended configuration
          of the other two — never the full cross product. Numbers are pulled
          from the latest run; open any row for its complete metric bundle.
        </Text>
        <HStack gap="3" wrap="wrap">
          <Text textStyle="data" color="fg.subtle">
            Run {run.id} · {formatAbsoluteTime(run.created_at)}
          </Text>
          {run.corpus_version ? (
            <Text textStyle="data" color="fg.subtle">corpus {run.corpus_version}</Text>
          ) : null}
          {run.git_sha ? (
            <Text textStyle="data" color="fg.subtle">{run.git_sha}</Text>
          ) : null}
          <Text textStyle="data" color="fg.subtle">
            {formatCount(run.metrics.sample_size, "gold question")}
          </Text>
        </HStack>
        {run.notes ? (
          <Text textStyle="small" color="fg.muted">{run.notes}</Text>
        ) : null}
      </Stack>

      <AblationTable results={run.results} onDrillIn={setDrillIn} />

      <Stack as="section" gap="3">
        <Heading as="h3" textStyle="subheading">
          Confidence calibration
        </Heading>
        <Text textStyle="body" color="fg.muted" maxW="measure">
          Predicted confidence against observed accuracy — a well-calibrated
          extractor sits on the diagonal, so "80% confident" means right about
          80% of the time, not just "more confident than the alternative."
        </Text>
        <CalibrationChart bins={CALIBRATION.bins} eceBefore={CALIBRATION.ece_before} eceAfter={CALIBRATION.ece_after} />
      </Stack>

      <Stack as="section" gap="3">
        <Heading as="h3" textStyle="subheading">
          Trend across runs
        </Heading>
        <MetricTrendChart runs={EVAL_RUNS} />
      </Stack>

      <MetricDrawer result={drillIn} onClose={() => { setDrillIn(null); }} />
    </Stack>
  );
};

export default EvalsScreen;

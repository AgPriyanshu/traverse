import { STAGE_ORDER } from "@/lib/api";
import type { StageStatus } from "@/lib/api";

/**
 * A fallback for when the API has not populated `estimated_seconds_remaining`
 * (it is optional in the contract, and nothing in this sprint's backend work
 * computes it yet). Averages this book's own completed-stage durations —
 * which already reflect its own page count, since that is what produced
 * them — and multiplies by the stages still ahead, crediting a running
 * stage for the time it has already spent (PRD F1.1: invisible progress
 * reads as broken).
 */
export const estimateSecondsRemaining = (
  stages: StageStatus[] | undefined,
): number | null => {
  if (!stages || stages.length === 0) { return null; }

  const byName = new Map(stages.map((stage) => [stage.stage, stage]));

  const completedDurationsMs = stages
    .filter(
      (stage): stage is StageStatus & { duration_ms: number } =>
        stage.state === "succeeded" && typeof stage.duration_ms === "number",
    )
    .map((stage) => stage.duration_ms);

  if (completedDurationsMs.length === 0) { return null; }

  const averageMs =
    completedDurationsMs.reduce((sum, ms) => sum + ms, 0) /
    completedDurationsMs.length;

  const remainingStages = STAGE_ORDER.filter((name) => {
    const state = byName.get(name)?.state ?? "pending";
    return state === "pending" || state === "running";
  });

  if (remainingStages.length === 0) { return 0; }

  const runningElapsedMs = remainingStages.reduce((sum, name) => {
    const stage = byName.get(name);
    if (stage?.state !== "running" || !stage.started_at) { return sum; }
    const elapsed = Date.now() - new Date(stage.started_at).getTime();
    return sum + Math.max(elapsed, 0);
  }, 0);

  const remainingMs = Math.max(
    remainingStages.length * averageMs - runningElapsedMs,
    0,
  );
  return Math.round(remainingMs / 1000);
};

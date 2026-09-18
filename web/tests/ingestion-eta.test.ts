import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { StageStatus } from "@/lib/api";
import { estimateSecondsRemaining } from "@/lib/ingestion-eta";

const stage = (overrides: Partial<StageStatus>): StageStatus => ({
  stage: "pipeline.parse_and_chunk",
  state: "pending",
  attempt: 1,
  started_at: null,
  finished_at: null,
  duration_ms: null,
  error: null,
  ...overrides,
});

describe("estimateSecondsRemaining", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-18T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("says nothing with no stage reports yet", () => {
    expect(estimateSecondsRemaining(undefined)).toBeNull();
    expect(estimateSecondsRemaining([])).toBeNull();
  });

  it("says nothing before any stage has finished", () => {
    const stages = [
      stage({ stage: "pipeline.parse_and_chunk", state: "running" }),
    ];
    expect(estimateSecondsRemaining(stages)).toBeNull();
  });

  it("averages completed durations across the stages still ahead", () => {
    const stages: StageStatus[] = [
      stage({ stage: "pipeline.parse_and_chunk", state: "succeeded", duration_ms: 1000 }),
      stage({ stage: "pipeline.segment_chapters", state: "succeeded", duration_ms: 3000 }),
    ];
    // Average 2000ms · 7 stages still pending (9 total − 2 done) = 14000ms.
    expect(estimateSecondsRemaining(stages)).toBe(14);
  });

  it("credits a running stage for time it has already spent", () => {
    const stages: StageStatus[] = [
      stage({ stage: "pipeline.parse_and_chunk", state: "succeeded", duration_ms: 1000 }),
      stage({ stage: "pipeline.segment_chapters", state: "succeeded", duration_ms: 3000 }),
      stage({
        stage: "pipeline.embed_chunks",
        state: "running",
        started_at: "2026-09-18T11:59:55Z",
      }),
    ];
    // 14000ms baseline minus the 5000ms this running stage has already used.
    expect(estimateSecondsRemaining(stages)).toBe(9);
  });

  it("never goes negative when the running stage has overrun the average", () => {
    const stages: StageStatus[] = [
      stage({ stage: "pipeline.parse_and_chunk", state: "succeeded", duration_ms: 1000 }),
      stage({
        stage: "pipeline.segment_chapters",
        state: "running",
        started_at: "2026-09-18T11:00:00Z",
      }),
    ];
    expect(estimateSecondsRemaining(stages)).toBe(0);
  });

  it("returns zero once nothing is left pending or running", () => {
    const stages: StageStatus[] = [
      "pipeline.parse_and_chunk",
      "pipeline.segment_chapters",
      "pipeline.embed_chunks",
      "pipeline.extract_characters",
      "pipeline.resolve_aliases",
      "pipeline.reconcile_characters",
      "relations.extract",
      "relations.aggregate",
      "graph.upsert",
    ].map((name) =>
      stage({
        stage: name as StageStatus["stage"],
        state: "succeeded",
        duration_ms: 500,
      }),
    );
    expect(estimateSecondsRemaining(stages)).toBe(0);
  });
});

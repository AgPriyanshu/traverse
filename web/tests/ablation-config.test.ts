import { describe, expect, it } from "vitest";
import { baselineFor, configSummary, deltaFor, isBaseline, isRecommended } from "@/routes/ops/evals/ablation-config";
import type { AblationConfig, EvalResultOut, MetricSet } from "@/routes/ops/evals/types";

const config = (overrides: Partial<AblationConfig> = {}): AblationConfig => ({
  axis: "extraction",
  label: "test",
  extraction_mode: null,
  alias_mode: null,
  with_human_review: false,
  retrieval_mode: null,
  model_mode: null,
  ...overrides,
});

const metrics = (overrides: Partial<MetricSet> = {}): MetricSet => ({
  precision: null, recall: null, f1: null, accuracy: null, ece: null, spoiler_leakage_rate: null, sample_size: 0,
  ...overrides,
});

describe("isRecommended / isBaseline", () => {
  it("flags two-pass + full-cascade (no human review) as the extraction recommendation", () => {
    expect(isRecommended(config({ extraction_mode: "two_pass", alias_mode: "full_cascade" }))).toBe(true);
    expect(isRecommended(config({ extraction_mode: "two_pass", alias_mode: "full_cascade", with_human_review: true }))).toBe(false);
  });

  it("flags single-pass + string-only as the extraction baseline", () => {
    expect(isBaseline(config({ extraction_mode: "single_pass", alias_mode: "string_only" }))).toBe(true);
    expect(isBaseline(config({ extraction_mode: "two_pass", alias_mode: "string_only" }))).toBe(false);
  });

  it("flags graph-constrained retrieval and a routed model as recommended", () => {
    expect(isRecommended(config({ axis: "retrieval", retrieval_mode: "graph_constrained" }))).toBe(true);
    expect(isRecommended(config({ axis: "model", model_mode: "routed" }))).toBe(true);
  });
});

describe("configSummary", () => {
  it("renders only the flags that are set, in a stable order", () => {
    expect(configSummary(config({ extraction_mode: "two_pass", alias_mode: "full_cascade" }))).toBe(
      "two-pass, full alias cascade",
    );
    expect(configSummary(config({ axis: "model", model_mode: "routed" }))).toBe("routed");
  });
});

describe("deltaFor", () => {
  it("treats a lower ECE as an improvement", () => {
    const delta = deltaFor("ece", metrics({ ece: 0.05 }), metrics({ ece: 0.1 }));
    expect(delta).toEqual({ value: -0.05, improved: true });
  });

  it("treats a higher F1 as an improvement", () => {
    const delta = deltaFor("f1", metrics({ f1: 0.9 }), metrics({ f1: 0.8 }));
    expect(delta).toEqual({ value: expect.closeTo(0.1, 10), improved: true });
  });

  it("returns null when either side doesn't measure that metric", () => {
    expect(deltaFor("precision", metrics({ precision: 0.9 }), metrics({ precision: null }))).toBeNull();
  });
});

describe("baselineFor", () => {
  it("finds the one row in a set that matches the axis's baseline config", () => {
    const results: EvalResultOut[] = [
      { id: "a", eval_run_id: "r", axis: "extraction", label: "baseline", book_key: null, config: config({ extraction_mode: "single_pass", alias_mode: "string_only" }), metrics: metrics() },
      { id: "b", eval_run_id: "r", axis: "extraction", label: "improved", book_key: null, config: config({ extraction_mode: "two_pass", alias_mode: "full_cascade" }), metrics: metrics() },
    ];
    expect(baselineFor(results)?.id).toBe("a");
  });
});

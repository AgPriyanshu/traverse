import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderRoute } from "./render";

const jsonResponse = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );

const METRICS = {
  book_id: null,
  stages: [
    { stage: "character_extract", input_tokens: 1000, output_tokens: 200, cost_usd: 1.94, duration_ms: 40000 },
    { stage: "relation_extract", input_tokens: 1400, output_tokens: 300, cost_usd: 2.02, duration_ms: 55000 },
    { stage: "chapter_classify", input_tokens: 200, output_tokens: 20, cost_usd: 0.61, duration_ms: 5000 },
  ],
  total_cost_usd: 4.57,
  prefix_cache_hit_rate: 0.86,
};

const PROJECTS = [
  { id: "p-1", name: "Pride and Prejudice", slug: "pride-and-prejudice", kind: "standalone", book_count: 1, character_count: 45, relation_count: 24, updated_at: "2026-09-20T00:00:00Z" },
];

const QUERY_LATENCY = {
  project_id: "p-1",
  sample_count: 128,
  total_ms: { p50: 1800, p95: 4200, p99: 5100, n: 128 },
  ttft_ms: { p50: 300, p95: 900, p99: 1600, n: 128 },
  per_stage_ms: {
    retrieval: { p50: 400, p95: 900, p99: 1200, n: 128 },
    generation: { p50: 1100, p95: 3000, p99: 3800, n: 128 },
  },
  avg_cost_usd: 0.002,
  p95_within_budget: true,
  ttft_p95_within_budget: true,
  p95_budget_ms: 6000,
  ttft_budget_ms: 1500,
  violations: [],
};

const BOOKS = [
  { id: "b-1", project_id: "p-1", title: "Pride and Prejudice", status: "ready", created_at: "2026-09-01T00:00:00Z" },
];

const PIPELINE_RUNS = [
  {
    run_id: "run-1",
    book_id: "b-1",
    stages: [{ stage: "graph.upsert", state: "succeeded", attempt: 1, started_at: null, finished_at: null, duration_ms: 100, error: null }],
    trace_url: "https://langfuse.example/trace/run-1",
  },
];

const REVIEW_ALERTS = {
  project_id: null,
  generated_at: "2026-09-29T00:00:00Z",
  queue_depth_threshold: 50,
  queue_depth_total: 3,
  queue_depth_breached: false,
  stale_task_threshold_hours: 48,
  stale_tasks: [{ id: "t-1", task_type: "merge_characters", priority: 1, age_hours: 68.5 }],
  orphaned_threads: [],
  has_alerts: true,
};

const modelResult = (id: string, label: string, modelMode: string, accuracy: number) => ({
  id,
  eval_run_id: "run-eval-1",
  axis: "model",
  label,
  book_key: null,
  config: {
    axis: "model",
    label,
    extraction_mode: null,
    alias_mode: null,
    with_human_review: false,
    retrieval_mode: null,
    model_mode: modelMode,
  },
  metrics: { precision: null, recall: null, f1: null, accuracy, ece: null, spoiler_leakage_rate: null, sample_size: 38 },
});

const EVAL_RUN = {
  id: "run-eval-1",
  corpus_version: "2026-09-26",
  git_sha: "abc123",
  metrics: { precision: null, recall: null, f1: null, accuracy: 0.81, ece: null, spoiler_leakage_rate: null, sample_size: 38 },
  notes: null,
  results: [
    modelResult("m-local", "Local", "local", 0.79),
    modelResult("m-routed", "Routed", "routed", 0.81),
    modelResult("m-frontier", "Frontier", "frontier", 0.86),
  ],
  created_at: "2026-09-26T00:00:00Z",
};

type MockError = { __mockError: true; body: unknown; status: number };

const erroring = (body: unknown, status: number): MockError => ({ __mockError: true, body, status });

const isMockError = (value: unknown): value is MockError =>
  value !== null && typeof value === "object" && (value as { __mockError?: unknown }).__mockError === true;

function mockApi(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes("/api/health")) {
        return jsonResponse({ status: "ok", dependencies: [] });
      }
      const match = Object.entries(routes).find(([path]) => url.includes(path));
      if (match) {
        const value = match[1];
        return isMockError(value) ? jsonResponse(value.body, value.status) : jsonResponse(value);
      }
      return jsonResponse({ detail: `unhandled in test: ${url}` }, 404);
    }),
  );
}

describe("the ops dashboard", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders live cost, performance and health telemetry", async () => {
    mockApi({
      "/api/ops/metrics": METRICS,
      "/api/projects": PROJECTS,
      "/api/ops/query-latency": QUERY_LATENCY,
      "/api/books": BOOKS,
      "/api/ops/pipeline/runs": PIPELINE_RUNS,
      "/api/ops/pipeline/dead-letter": [],
      "/api/ops/review-alerts": REVIEW_ALERTS,
      "/api/ops/routing-policy": erroring({ detail: "Not implemented yet." }, 501),
      "/api/ops/eval-runs/latest": EVAL_RUN,
    });

    renderRoute("/ops");

    expect(await screen.findByText("$4.57")).toBeInTheDocument();
    expect(screen.getByText("Character extraction (pass 1)")).toBeInTheDocument();

    expect(await screen.findByText(/128 queries/i)).toBeInTheDocument();
    expect(screen.getByText("4.2 s")).toBeInTheDocument();

    expect(await screen.findByText(/pride and prejudice/i)).toBeInTheDocument();
    expect(screen.getByText(/1 task open past 48h/i)).toBeInTheDocument();
  });

  it("moves cost-per-query and accuracy together when the routing policy changes", async () => {
    const user = userEvent.setup();
    mockApi({
      "/api/ops/metrics": METRICS,
      "/api/projects": PROJECTS,
      "/api/ops/query-latency": QUERY_LATENCY,
      "/api/books": BOOKS,
      "/api/ops/pipeline/runs": [],
      "/api/ops/pipeline/dead-letter": [],
      "/api/ops/review-alerts": { ...REVIEW_ALERTS, has_alerts: false, stale_tasks: [] },
      "/api/ops/routing-policy": erroring({ detail: "Not implemented yet." }, 501),
      "/api/ops/eval-runs/latest": EVAL_RUN,
    });

    renderRoute("/ops");

    const answerSelect = await screen.findByLabelText(/answering a query/i);
    const costTile = (await screen.findByText("Cost per query")).closest("div") as HTMLElement;
    const accuracyTile = (await screen.findByText("Answer accuracy")).closest("div") as HTMLElement;

    const costBefore = within(costTile.parentElement as HTMLElement).getByText(/^\$/).textContent;
    const accuracyBefore = within(accuracyTile.parentElement as HTMLElement).getByText(/%$/).textContent;

    await user.selectOptions(answerSelect, "frontier");

    await waitFor(() => {
      const costAfter = within(costTile.parentElement as HTMLElement).getByText(/^\$/).textContent;
      expect(costAfter).not.toBe(costBefore);
    });
    const accuracyAfter = within(accuracyTile.parentElement as HTMLElement).getByText(/%$/).textContent;
    expect(accuracyAfter).not.toBe(accuracyBefore);
    expect(accuracyAfter).toBe("86.0%");
  });
});

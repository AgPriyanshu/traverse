import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DesignSystemProvider } from "@/design-system/provider";
import type { StageStatus } from "@/lib/api";
import { StageStepper } from "@/routes/book/stage-stepper";

const renderStepper = (
  stages: StageStatus[],
  props: Partial<React.ComponentProps<typeof StageStepper>> = {},
) => {
  return render(
    <DesignSystemProvider>
      <StageStepper stages={stages} {...props} />
    </DesignSystemProvider>,
  );
};

const failedStage: StageStatus = {
  stage: "pipeline.embed_chunks",
  state: "failed",
  attempt: 2,
  started_at: null,
  finished_at: null,
  duration_ms: null,
  error: "vLLM timed out",
};

describe("StageStepper", () => {
  it("offers no retry when the caller has not wired one up", () => {
    renderStepper([failedStage]);
    expect(
      screen.queryByRole("button", { name: /retry from this stage/i }),
    ).not.toBeInTheDocument();
  });

  it("retries the failed stage by name, not by position", () => {
    const onRetryStage = vi.fn();
    renderStepper([failedStage], { onRetryStage });

    screen.getByRole("button", { name: /retry from this stage/i }).click();

    expect(onRetryStage).toHaveBeenCalledWith("pipeline.embed_chunks");
  });

  it("shows the failure text next to the stage it belongs to", () => {
    renderStepper([failedStage]);
    expect(screen.getByText("vLLM timed out")).toBeInTheDocument();
  });

  it("marks only the stage currently retrying as loading", () => {
    const onRetryStage = vi.fn();
    renderStepper([failedStage], {
      onRetryStage,
      retryingStage: "pipeline.embed_chunks",
    });

    expect(
      screen.getByRole("button", { name: /retrying/i }),
    ).toBeInTheDocument();
  });
});

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { expectNoAxeViolations } from "./axe";
import { renderRoute } from "./render";

describe("the eval results screen (S8.7)", () => {
  it("groups the ablation matrix by axis and marks the recommended row", async () => {
    renderRoute("/ops/evals");

    expect(await screen.findByRole("heading", { name: /evaluation results/i })).toBeInTheDocument();

    const extraction = screen.getByRole("heading", { name: /^extraction$/i }).closest("section") as HTMLElement;
    expect(within(extraction).getAllByText(/two-pass, full alias cascade/i).length).toBeGreaterThan(0);
    expect(within(extraction).getAllByText(/recommended/i).length).toBeGreaterThan(0);
    expect(within(extraction).getByText(/^baseline$/i)).toBeInTheDocument();

    const retrieval = screen.getByRole("heading", { name: /^retrieval$/i }).closest("section") as HTMLElement;
    expect(within(retrieval).getAllByText(/graph-constrained/i).length).toBeGreaterThan(0);

    const model = screen.getByRole("heading", { name: /^model$/i }).closest("section") as HTMLElement;
    expect(within(model).getAllByText(/routed/i).length).toBeGreaterThan(0);
  });

  it("has no automatically detectable accessibility violations (S9.12)", async () => {
    const { container } = renderRoute("/ops/evals");
    await screen.findByRole("heading", { name: /evaluation results/i });

    await expectNoAxeViolations(container);
  });

  it("shows a delta against the axis baseline for a non-baseline row", async () => {
    renderRoute("/ops/evals");
    await screen.findByRole("heading", { name: /evaluation results/i });

    const extraction = screen.getByRole("heading", { name: /^extraction$/i }).closest("section") as HTMLElement;
    // Two-pass/full-cascade beats the single-pass/string-only baseline — the
    // improvement direction (▲) is shown, never colour alone.
    expect(within(extraction).getAllByText(/▲.*vs\. baseline/i).length).toBeGreaterThan(0);
  });

  it("drills a row into its full metric bundle, including fields the headline columns don't show", async () => {
    const user = userEvent.setup();
    renderRoute("/ops/evals");
    await screen.findByRole("heading", { name: /evaluation results/i });

    const retrieval = screen.getByRole("heading", { name: /^retrieval$/i }).closest("section") as HTMLElement;
    // The label's parenthetical is unique to the row heading, unlike
    // "graph-constrained" which also appears in the row's own config summary.
    const row = within(retrieval).getByText(/roster \+ evidence first/i).closest("tr") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: /full metrics/i }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/spoiler leakage/i)).toBeInTheDocument();
    // Precision/recall don't apply to a retrieval-axis cell in this fixture —
    // the drawer says so rather than showing a fabricated number.
    expect(within(dialog).getAllByText(/n\/a for this axis/i).length).toBeGreaterThan(0);
  });

  it("renders the calibration chart with the diagonal labelled and both ECE figures", async () => {
    renderRoute("/ops/evals");
    await screen.findByRole("heading", { name: /evaluation results/i });

    expect(screen.getByText(/perfect calibration/i)).toBeInTheDocument();
    expect(screen.getByText(/ece before calibration/i)).toBeInTheDocument();
    expect(screen.getByText(/ece after calibration/i)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /reliability diagram/i })).toBeInTheDocument();
    // The chart's accessible table equivalent.
    expect(
      screen.getByRole("table", { name: /calibration bins as a table/i }),
    ).toBeInTheDocument();
  });

  it("renders the metric trend across the fixture's three runs", async () => {
    renderRoute("/ops/evals");
    await screen.findByRole("heading", { name: /evaluation results/i });

    expect(screen.getByText(/overall f1/i)).toBeInTheDocument();
    expect(screen.getByText(/spoiler leakage rate/i)).toBeInTheDocument();
    expect(screen.getAllByText(/over 3 runs/i).length).toBe(2);
  });
});

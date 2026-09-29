import { screen, waitFor } from "@testing-library/react";
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

function mockApi(routes: Record<string, [unknown, number] | unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes("/api/health")) {
        return jsonResponse({ status: "ok", dependencies: [] });
      }
      const match = Object.entries(routes).find(([path]) => url.includes(path));
      if (!match) { return jsonResponse({ detail: `unhandled in test: ${url}` }, 404); }
      const [body, status] = Array.isArray(match[1]) && match[1].length === 2 && typeof match[1][1] === "number"
        ? (match[1] as [unknown, number])
        : [match[1], 200];
      return jsonResponse(body, status);
    }),
  );
}

/**
 * S9.11, ETH-4/NFR-residency: a query or an upload leaving the machine must
 * be visibly labelled at the point of use, not only in a settings page.
 * `GET /ops/routing-policy` is still be2's S9.6 stub in this worktree
 * (501), so these tests cover both that fallback (fully local by default —
 * `DEFAULT_POLICY`, `@/lib/inference-mode`) and a live policy that routes to
 * a frontier API, to prove the indicator and the upload consent gate react
 * to either.
 */
describe("inference-mode labelling", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows the fully-local indicator when the routing policy is unavailable", async () => {
    mockApi({ "/api/ops/routing-policy": [{ detail: "Not implemented yet." }, 501] });

    renderRoute("/books");

    expect(await screen.findByText(/fully local/i)).toBeInTheDocument();
  });

  it("shows the frontier indicator when the live policy routes answering to an API", async () => {
    mockApi({
      "/api/ops/routing-policy": {
        version: 3,
        purposes: { answer: "frontier", judge: "frontier" },
      },
    });

    renderRoute("/books");

    expect(await screen.findByText(/frontier api — leaves this machine/i)).toBeInTheDocument();
  });

  it("lets an upload proceed with no consent step when extraction stays fully local", async () => {
    mockApi({
      "/api/ops/routing-policy": [{ detail: "Not implemented yet." }, 501],
      "/api/projects": [],
    });

    renderRoute("/books/upload");

    expect(
      await screen.findByText(/fully local — this book's content never leaves this machine/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("blocks upload on an unchecked consent box when extraction routes to a frontier API", async () => {
    const user = userEvent.setup();
    mockApi({
      "/api/ops/routing-policy": {
        version: 3,
        purposes: { character_extract: "frontier", relation_extract: "frontier" },
      },
      "/api/projects": [],
    });

    renderRoute("/books/upload");

    expect(
      await screen.findByText(/sent to a frontier api for character extraction, relationship extraction/i),
    ).toBeInTheDocument();

    const checkbox = screen.getByRole("checkbox", { name: /leave this machine/i });
    expect(checkbox).not.toBeChecked();

    const submit = screen.getByRole("button", { name: /start ingestion/i });
    expect(submit).toBeDisabled();

    await user.click(checkbox);
    await waitFor(() => { expect(checkbox).toBeChecked(); });
    // Still disabled — no file chosen and no project name yet, independent of consent.
    expect(submit).toBeDisabled();
  });
});

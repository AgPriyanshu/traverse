import { screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderRoute } from "./render";

/** Every frozen handler answers like this until its story lands. */
const notImplemented = (path: string) =>
  new Response(
    JSON.stringify({ detail: `Not implemented yet — owned by be1, ${path}.` }),
    { status: 501, headers: { "content-type": "application/json" } },
  );

const ROUTES: [path: string, heading: RegExp][] = [
  // The landing screen's own heading is static, not data-derived, so it
  // renders the same whether `useProjects()` 501s (this file's default
  // mock) or succeeds — unlike most rows below.
  ["/", /ask a novel anything/i],
  ["/books", /library/i],
  ["/books/upload", /add a book/i],
  ["/books/abc-123", /ingestion/i],
  ["/books/abc-123/chapters", /chapters/i],
  ["/books/abc-123/pages/12", /page 12/i],
  // The ask screens (S6.10-S6.13) and the review queue (S7.8) resolve their
  // scope from `useBook`/`useProject` before rendering anything else, so a
  // 501 there surfaces the frozen contract's own error state, same as every
  // other real screen below.
  ["/books/abc-123/ask", /not built yet/i],
  ["/books/abc-123/review", /not built yet/i],
  // Real screens as of S3.10/S3.11/S5.9-S5.12, now project-scoped — every
  // API call 501s under this test's default mock, so each surfaces the
  // frozen contract's own "not built yet" error state rather than the
  // generic `<NotYetBuilt>` placeholder.
  ["/projects", /not built yet/i],
  // `/projects/new` makes no API call until submit, so it renders its own
  // real heading rather than the frozen contract's 501 error state.
  ["/projects/new", /new project/i],
  ["/projects/p-1", /not built yet/i],
  ["/projects/p-1/characters", /not built yet/i],
  ["/projects/p-1/characters/c-1", /not built yet/i],
  ["/projects/p-1/graph", /not built yet/i],
  ["/projects/p-1/ask", /not built yet/i],
  // Real as of S9.10 — every panel calls its own live endpoint and each
  // 501s independently under this test's default mock, so several "Not
  // built yet" headings render at once; the dashboard's own static "Operations"
  // heading (not data-derived) is the one unique match.
  ["/ops", /^operations$/i],
  // Real as of S8.7 — fixture-backed (no live route yet, see
  // plans/sprint-8/HANDOFF.md), so it renders without an API call at all.
  ["/ops/evals", /evaluation results/i],
  ["/nowhere", /there is no page here/i],
];

let consoleError: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      // `openapi-fetch` calls the configured `fetch` with a `Request`
      // instance, not a bare URL string — `.url` has the real address.
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes("/api/health")) {
        return Promise.resolve(
          new Response(JSON.stringify({ status: "degraded", dependencies: [] }), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        );
      }
      return Promise.resolve(notImplemented(url));
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("the route table", () => {
  it.each(ROUTES)("renders %s without a console error", async (path, heading) => {
    renderRoute(path);
    expect(
      await screen.findByRole("heading", { name: heading }),
    ).toBeInTheDocument();
    expect(consoleError).not.toHaveBeenCalled();
  });

  it("renders the public landing screen at the root (S9.13)", async () => {
    renderRoute("/");
    expect(
      await screen.findByRole("heading", { name: /ask a novel anything/i }),
    ).toBeInTheDocument();
  });

  it("puts the skip link first in the tab order", async () => {
    renderRoute("/books");
    const skip = await screen.findByRole("link", { name: /skip to content/i });
    expect(skip).toHaveAttribute("href", "#main");
  });

  it("renders the 501 from the library as the API's own message", async () => {
    renderRoute("/books");
    await waitFor(() =>
      expect(screen.getByText(/not implemented yet/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/HTTP 501/)).toBeInTheDocument();
  });
});

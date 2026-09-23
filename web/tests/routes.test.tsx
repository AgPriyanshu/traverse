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
  ["/books", /library/i],
  ["/books/upload", /add a book/i],
  ["/books/abc-123", /ingestion/i],
  ["/books/abc-123/chapters", /chapters/i],
  ["/books/abc-123/pages/12", /page 12/i],
  // Real screens as of S3.10/S3.11 — every API call 501s under this test's
  // default mock, so both surface the frozen contract's own "not built yet"
  // error state rather than the generic `<NotYetBuilt>` placeholder.
  ["/books/abc-123/characters", /not built yet/i],
  ["/books/abc-123/characters/c-1", /not built yet/i],
  ["/books/abc-123/graph", /the graph explorer is not built yet/i],
  ["/books/abc-123/ask", /ask is not built yet/i],
  ["/books/abc-123/review", /the review queue is not built yet/i],
  ["/projects", /projects is not built yet/i],
  ["/projects/new", /new project is not built yet/i],
  ["/projects/p-1", /project overview is not built yet/i],
  ["/projects/p-1/characters", /the series roster is not built yet/i],
  ["/projects/p-1/graph", /the series graph is not built yet/i],
  ["/projects/p-1/ask", /ask is not built yet/i],
  ["/ops", /the operations dashboard is not built yet/i],
  ["/ops/evals", /eval ablations is not built yet/i],
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

  it("redirects the root to the library", async () => {
    renderRoute("/");
    expect(
      await screen.findByRole("heading", { name: /library/i }),
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

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { moveBefore, moveBook, orderOf } from "@/routes/project/reorder-books";
import { nextSeriesOrder } from "@/routes/project/project-lookup";
import { renderRoute } from "./render";

const PROJECT_ID = "project-1";
const BOOK_1 = "book-1";
const BOOK_2 = "book-2";

const jsonResponse = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }),
  );

function mockApi(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = input instanceof Request ? input.url : String(input);
      const match = Object.entries(routes)
        .sort(([a], [b]) => b.length - a.length)
        .find(([path]) => url.includes(path));
      return match ? jsonResponse(match[1]) : jsonResponse({ detail: `unhandled: ${url}` }, 404);
    }),
  );
}

const book = (overrides: Record<string, unknown> = {}) => ({
  id: BOOK_1,
  project_id: PROJECT_ID,
  series_order: 1,
  title: "Anne of Green Gables",
  author: "L. M. Montgomery",
  page_count: 300,
  chapter_count: 38,
  character_count: 3,
  status: "ready",
  ingested_at: "2026-09-01T00:00:00Z",
  ...overrides,
});

const project = (overrides: Record<string, unknown> = {}) => ({
  id: PROJECT_ID,
  name: "Anne of Green Gables",
  slug: "anne",
  kind: "series",
  book_count: 2,
  character_count: 3,
  relation_count: 1,
  updated_at: "2026-09-01T00:00:00Z",
  books: [book(), book({ id: BOOK_2, series_order: 2, title: "Anne of Avonlea" })],
  ...overrides,
});

describe("reorder-books helpers", () => {
  it("moves a book up or down a slot", () => {
    const order = ["a", "b", "c"];
    expect(moveBook(order, "b", -1)).toEqual(["b", "a", "c"]);
    expect(moveBook(order, "b", 1)).toEqual(["a", "c", "b"]);
    expect(moveBook(order, "a", -1)).toEqual(order);
    expect(moveBook(order, "c", 1)).toEqual(order);
  });

  it("moves a dragged book before its drop target", () => {
    expect(moveBefore(["a", "b", "c"], "c", "a")).toEqual(["c", "a", "b"]);
    expect(moveBefore(["a", "b", "c"], "a", "c")).toEqual(["b", "a", "c"]);
  });

  it("suggests the next open series slot", () => {
    expect(nextSeriesOrder([])).toBe(1);
    expect(nextSeriesOrder([{ series_order: 1 }, { series_order: 3 }] as never)).toBe(4);
  });

  it("orders books by series_order for the mutation payload", () => {
    expect(orderOf([{ id: "y", series_order: 2 }, { id: "x", series_order: 1 }] as never)).toEqual(["x", "y"]);
  });
});

describe("the projects list", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows an empty state with a way to create the first project", async () => {
    mockApi({ "/api/projects": [] });
    renderRoute("/projects");
    expect(await screen.findByText(/no projects yet/i)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /new project/i }).length).toBeGreaterThan(0);
  });

  it("lists projects with their counts", async () => {
    mockApi({ "/api/projects": [project()] });
    renderRoute("/projects");
    expect(await screen.findByRole("heading", { name: "Anne of Green Gables" })).toBeInTheDocument();
    expect(screen.getByText(/2 books/i)).toBeInTheDocument();
    expect(screen.getByText(/3 characters/i)).toBeInTheDocument();
  });
});

describe("creating a project", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("creates the project and opens it", async () => {
    mockApi({
      "/api/projects/project-2": { ...project(), id: "project-2", name: "The Hobbit", books: [] },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = input instanceof Request ? input.url : String(input);
        const method = input instanceof Request ? input.method : "GET";
        if (url.includes("/api/projects") && !url.includes("project-2") && method === "POST") {
          return jsonResponse({ id: "project-2", name: "The Hobbit", slug: "the-hobbit", kind: "standalone", book_count: 0, character_count: 0, relation_count: 0, updated_at: null });
        }
        if (url.includes("/api/projects/project-2")) {
          return jsonResponse({ ...project(), id: "project-2", name: "The Hobbit", books: [] });
        }
        return jsonResponse({ detail: `unhandled: ${url}` }, 404);
      }),
    );

    renderRoute("/projects/new");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/project name/i), "The Hobbit");
    await user.click(screen.getByRole("button", { name: /create project/i }));

    expect(await screen.findByRole("heading", { name: "The Hobbit" })).toBeInTheDocument();
  });
});

describe("the project overview", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("lists books in series order and reorders with the move-down button", async () => {
    let patchBody: unknown;
    vi.stubGlobal(
      "fetch",
      // `openapi-fetch`'s configured `fetch` is called with a single `Request`
      // instance, never a `(url, init)` pair — the body has to be read off
      // that `Request`, not a second argument (web-app.md's own gotcha).
      vi.fn(async (input: RequestInfo | URL) => {
        const url = input instanceof Request ? input.url : String(input);
        if (url.includes(`/api/projects/${PROJECT_ID}/order`)) {
          patchBody = input instanceof Request ? await input.clone().json() : undefined;
          // A short delay so the "recomputing" banner has a real pending
          // window to assert against, rather than racing a same-tick mock.
          await new Promise((resolve) => setTimeout(resolve, 20));
          return jsonResponse(project());
        }
        if (url.includes(`/api/projects/${PROJECT_ID}`)) {
          return jsonResponse(project());
        }
        return jsonResponse({ detail: `unhandled: ${url}` }, 404);
      }),
    );

    renderRoute(`/projects/${PROJECT_ID}`);
    await screen.findByRole("heading", { name: "Anne of Green Gables" });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /move anne of green gables later/i }));

    // The recomputing banner is the immediate, optimistic state right after
    // the mutation fires — assert it before waiting on the (already
    // resolved-by-then) mock request below.
    expect(await screen.findByRole("status")).toHaveTextContent(/recomputing/i);

    await waitFor(() => {
      expect(patchBody).toEqual({ order: [BOOK_2, BOOK_1] });
    });
  });

  it("prefills the add-book series order to the next open slot", async () => {
    mockApi({ [`/api/projects/${PROJECT_ID}`]: project() });
    renderRoute(`/projects/${PROJECT_ID}`);
    await screen.findByRole("heading", { name: "Anne of Green Gables" });
    expect(screen.getByLabelText(/series order/i)).toHaveValue("3");
  });
});

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderRoute } from "./render";

const PROJECT_ID = "project-1";
const BOOK_ID = "book-1";

const book = {
  id: BOOK_ID,
  project_id: PROJECT_ID,
  series_order: 1,
  title: "Anne of Green Gables",
  author: "L. M. Montgomery",
  page_count: 300,
  chapter_count: 10,
  character_count: 4,
  status: "ready",
  ingested_at: null,
};

const project = {
  id: PROJECT_ID,
  name: "Anne Series",
  slug: "anne",
  kind: "series",
  book_count: 1,
  character_count: 4,
  relation_count: 2,
  updated_at: null,
  books: [book],
};

const json = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }),
  );

type Call = { method: string; path: string };
const calls: Call[] = [];
let deleteStatus = 204;

const mockApi = () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const request = input instanceof Request ? input : null;
      const url = new URL(request ? request.url : String(input), "http://localhost");
      const method = (init?.method ?? request?.method ?? "GET").toUpperCase();
      calls.push({ method, path: url.pathname });

      if (method === "DELETE") {
        return deleteStatus === 204
          ? Promise.resolve(new Response(null, { status: 204 }))
          : json({ detail: "boom" }, deleteStatus);
      }
      if (url.pathname === `/api/books/${BOOK_ID}`) { return json(book); }
      if (url.pathname === `/api/projects/${PROJECT_ID}`) { return json(project); }
      if (url.pathname === "/api/books" || url.pathname === "/api/projects") { return json([]); }
      return json({ detail: `unhandled in test: ${url.pathname}` }, 404);
    }),
  );
};

const deletes = () => calls.filter((call) => call.method === "DELETE");

describe("deleting a book or a project", () => {
  beforeEach(() => {
    calls.length = 0;
    deleteStatus = 204;
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("names the book, asks first, and deletes nothing on cancel", async () => {
    mockApi();
    renderRoute(`/books/${BOOK_ID}`);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /delete book/i }));

    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText(/delete “anne of green gables”\?/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/cannot be undone/i)).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: /cancel/i }));

    await waitFor(() => { expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument(); });
    expect(deletes()).toHaveLength(0);
  });

  it("deletes the book and returns to the library", async () => {
    mockApi();
    renderRoute(`/books/${BOOK_ID}`);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /delete book/i }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: /^delete$/i }));

    await waitFor(() => {
      expect(deletes()).toEqual([{ method: "DELETE", path: `/api/books/${BOOK_ID}` }]);
    });
    expect(await screen.findByRole("heading", { name: /library/i, level: 1 })).toBeInTheDocument();
  });

  it("deletes a project and returns to the project list", async () => {
    mockApi();
    renderRoute(`/projects/${PROJECT_ID}`);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /delete project/i }));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText(/all 1 book in it are removed/i)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: /^delete$/i }));

    await waitFor(() => {
      expect(deletes()).toEqual([{ method: "DELETE", path: `/api/projects/${PROJECT_ID}` }]);
    });
    expect(await screen.findByRole("heading", { name: /^projects$/i, level: 1 })).toBeInTheDocument();
  });

  it("stays on the page with the dialog open when the delete fails", async () => {
    deleteStatus = 500;
    mockApi();
    const { router } = renderRoute(`/books/${BOOK_ID}`);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /delete book/i }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: /^delete$/i }));

    await waitFor(() => { expect(deletes()).toHaveLength(1); });
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/books/${BOOK_ID}`);
  });
});

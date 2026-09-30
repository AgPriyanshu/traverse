import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderRoute } from "./render";

const PROJECT_ID = "project-1";
const BOOK_1 = "book-1";
const BOOK_2 = "book-2";
const BOOK_3 = "book-3";

const project = (overrides: Record<string, unknown> = {}) => ({
  id: PROJECT_ID,
  name: "Anne of Green Gables",
  slug: "anne-of-green-gables",
  kind: "series",
  book_count: 3,
  character_count: 4,
  relation_count: 2,
  updated_at: "2026-09-01T00:00:00Z",
  books: [
    { id: BOOK_1, project_id: PROJECT_ID, series_order: 1, title: "Anne of Green Gables", author: "L. M. Montgomery", page_count: 300, chapter_count: 38, character_count: 3, status: "ready", ingested_at: "2026-09-01T00:00:00Z" },
    { id: BOOK_2, project_id: PROJECT_ID, series_order: 2, title: "Anne of Avonlea", author: "L. M. Montgomery", page_count: 280, chapter_count: 30, character_count: 3, status: "ready", ingested_at: "2026-09-01T00:00:00Z" },
    { id: BOOK_3, project_id: PROJECT_ID, series_order: 3, title: "Anne of the Island", author: "L. M. Montgomery", page_count: 260, chapter_count: 28, character_count: 3, status: "ready", ingested_at: "2026-09-01T00:00:00Z" },
  ],
  ...overrides,
});

const character = (overrides: Record<string, unknown> = {}) => ({
  id: "char-anne",
  project_id: PROJECT_ID,
  canonical_name: "Anne Shirley",
  aliases: ["Anne", "Carrots"],
  importance_tier: "protagonist",
  mention_count: 1142,
  first_page: 3,
  first_chapter: 1,
  first_book_id: BOOK_1,
  appears_in_books: [1],
  collision_suspected: false,
  human_verified: false,
  ...overrides,
});

const jsonResponse = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );

function mockApi(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = input instanceof Request ? input.url : String(input);
      const match = Object.entries(routes).find(([path]) => url.includes(path));
      if (match) { return jsonResponse(match[1]); }
      return jsonResponse({ detail: `unhandled in test: ${url}` }, 404);
    }),
  );
}

describe("the series roster", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("groups characters by tier, protagonists first", async () => {
    mockApi({
      [`/api/projects/${PROJECT_ID}/characters`]: [
        character({ id: "char-marilla", canonical_name: "Marilla Cuthbert", aliases: [], importance_tier: "minor", mention_count: 12, first_page: 200, appears_in_books: [1, 2, 3] }),
        character(),
      ],
      [`/api/projects/${PROJECT_ID}`]: project(),
    });

    renderRoute(`/projects/${PROJECT_ID}/characters`);

    await screen.findByText("Anne Shirley");
    const headings = screen.getAllByRole("heading", { level: 3 }).map((node) => node.textContent);
    expect(headings.indexOf("Protagonists")).toBeLessThan(headings.indexOf("Minor"));
  });

  it("gives Anne one row with an appearance strip across all three books", async () => {
    mockApi({
      [`/api/projects/${PROJECT_ID}/characters`]: [
        character({ appears_in_books: [1, 2, 3] }),
      ],
      [`/api/projects/${PROJECT_ID}`]: project(),
    });

    renderRoute(`/projects/${PROJECT_ID}/characters`);

    await screen.findByText("Anne Shirley");
    expect(screen.getAllByText("Anne Shirley")).toHaveLength(1);
    expect(screen.getByRole("img", { name: /anne shirley appears in books 1–3 of 3/i })).toBeInTheDocument();
    expect(screen.getByText(/books 1–3/i)).toBeInTheDocument();
  });

  it("filters to characters new in a given book", async () => {
    mockApi({
      [`/api/projects/${PROJECT_ID}/characters`]: [
        character({ appears_in_books: [1, 2, 3] }),
        character({
          id: "char-davy",
          canonical_name: "Davy Keith",
          aliases: [],
          first_book_id: BOOK_3,
          appears_in_books: [3],
          mention_count: 40,
          first_page: 12,
        }),
      ],
      [`/api/projects/${PROJECT_ID}`]: project(),
    });

    renderRoute(`/projects/${PROJECT_ID}/characters`);
    await screen.findByText("Davy Keith");

    // The row itself already flags a single-appearance character — the
    // filter is a second way to ask the same question, not the only one.
    expect(screen.getAllByText(/new in bk\. 3/i).length).toBeGreaterThanOrEqual(2);

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /new in bk\. 3/i }));

    await waitFor(() => {
      expect(screen.queryByText("Anne Shirley")).not.toBeInTheDocument();
      expect(screen.getByText("Davy Keith")).toBeInTheDocument();
    });
  });

  it("finds a character by a nickname the search box never shows", async () => {
    mockApi({
      [`/api/projects/${PROJECT_ID}/characters`]: [
        character(),
        character({ id: "char-gilbert", canonical_name: "Gilbert Blythe", aliases: ["Gilbert"], importance_tier: "protagonist", mention_count: 700, first_page: 15 }),
      ],
      [`/api/projects/${PROJECT_ID}`]: project(),
    });

    renderRoute(`/projects/${PROJECT_ID}/characters`);
    await screen.findByText("Gilbert Blythe");

    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: /search characters/i }), "Carrots");

    await waitFor(() => {
      expect(screen.getByText("Anne Shirley")).toBeInTheDocument();
      expect(screen.queryByText("Gilbert Blythe")).not.toBeInTheDocument();
    });
  });

  it("filters to a single tier and back", async () => {
    mockApi({
      [`/api/projects/${PROJECT_ID}/characters`]: [
        character(),
        character({ id: "char-footman", canonical_name: "A Footman", aliases: [], importance_tier: "mentioned", mention_count: 1, first_page: 90 }),
      ],
      [`/api/projects/${PROJECT_ID}`]: project(),
    });

    renderRoute(`/projects/${PROJECT_ID}/characters`);
    await screen.findByText("Anne Shirley");
    expect(screen.getByText("A Footman")).toBeInTheDocument();

    screen.getByRole("button", { name: /^mentioned \(1\)$/i }).click();

    await waitFor(() => {
      expect(screen.queryByText("Anne Shirley")).not.toBeInTheDocument();
      expect(screen.getByText("A Footman")).toBeInTheDocument();
    });
  });

  it("sorts by name", async () => {
    mockApi({
      [`/api/projects/${PROJECT_ID}/characters`]: [
        character({ id: "char-z", canonical_name: "Zeta Person", mention_count: 5, first_page: 5, aliases: [] }),
        character(),
      ],
      [`/api/projects/${PROJECT_ID}`]: project(),
    });

    renderRoute(`/projects/${PROJECT_ID}/characters`);
    await screen.findByText("Anne Shirley");

    screen.getByRole("button", { name: /^name$/i }).click();

    await waitFor(() => {
      const [list] = screen.getAllByRole("list").filter((candidate) => !candidate.closest("nav"));
      const names = within(list).getAllByRole("link").map((link) => link.textContent);
      const anneIndex = names.findIndex((name) => name?.includes("Anne"));
      const zetaIndex = names.findIndex((name) => name?.includes("Zeta"));
      expect(anneIndex).toBeLessThan(zetaIndex);
    });
  });

  it("shows an empty state when the roster has no characters yet", async () => {
    mockApi({
      [`/api/projects/${PROJECT_ID}/characters`]: [],
      [`/api/projects/${PROJECT_ID}`]: project(),
    });

    renderRoute(`/projects/${PROJECT_ID}/characters`);

    expect(await screen.findByText(/no characters yet/i)).toBeInTheDocument();
  });

  it("shows one book's cast inside that book, with links that stay in the book", async () => {
    mockApi({
      [`/api/projects/${PROJECT_ID}/characters`]: [
        character({ id: "char-marilla", canonical_name: "Marilla Cuthbert", importance_tier: "minor", appears_in_books: [1, 2] }),
        character({ id: "char-diana", canonical_name: "Diana Barry", importance_tier: "minor", appears_in_books: [2] }),
      ],
      [`/api/projects/${PROJECT_ID}`]: project(),
      [`/api/books/${BOOK_1}`]: project().books[0],
    });

    renderRoute(`/books/${BOOK_1}/characters`);

    const marilla = await screen.findByRole("link", { name: /marilla cuthbert/i });
    expect(marilla).toHaveAttribute("href", `/books/${BOOK_1}/characters/char-marilla`);
    expect(screen.queryByText("Diana Barry")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /everyone in anne of green gables/i, level: 2 })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: /new in book/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^characters$/i })).toHaveAttribute("href", `/books/${BOOK_1}/characters`);
  });

  it("puts a back link and a trail on the sub page", async () => {
    mockApi({
      [`/api/projects/${PROJECT_ID}/characters`]: [character()],
      [`/api/projects/${PROJECT_ID}`]: project(),
      [`/api/books/${BOOK_1}`]: project().books[0],
    });

    renderRoute(`/books/${BOOK_1}/characters`);

    const trail = await screen.findByRole("navigation", { name: /breadcrumb/i });
    expect(await within(trail).findByRole("link", { name: /^Books$/ })).toHaveAttribute("href", "/books");
    expect(await within(trail).findByRole("link", { name: /^Anne of Green Gables$/ })).toHaveAttribute("href", `/books/${BOOK_1}`);
    expect(within(trail).getByText("Characters")).toHaveAttribute("aria-current", "page");
    expect(within(trail).getByRole("link", { name: /back to anne of green gables/i })).toHaveAttribute("href", `/books/${BOOK_1}`);
  });

  it("shows no trail on a top-level page", async () => {
    mockApi({ "/api/projects": [] });

    renderRoute("/projects");

    await screen.findByRole("heading", { name: /^projects$/i, level: 1 });
    expect(screen.queryByRole("navigation", { name: /breadcrumb/i })).not.toBeInTheDocument();
  });
});

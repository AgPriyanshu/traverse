import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderRoute } from "./render";

const BOOK_ID = "book-1";
const PROJECT_ID = "project-1";

const book = (overrides: Record<string, unknown> = {}) => ({
  id: BOOK_ID,
  project_id: PROJECT_ID,
  series_order: null,
  title: "Pride and Prejudice",
  author: "Jane Austen",
  translator: null,
  page_count: 245,
  chapter_count: 61,
  status: "ready",
  ingested_at: "2026-09-01T00:00:00Z",
  ...overrides,
});

const character = (overrides: Record<string, unknown> = {}) => ({
  id: "char-elizabeth",
  project_id: PROJECT_ID,
  canonical_name: "Elizabeth Bennet",
  aliases: ["Elizabeth", "Lizzy", "Eliza", "Miss Bennet"],
  importance_tier: "protagonist",
  mention_count: 1142,
  first_page: 3,
  first_chapter: 1,
  first_book_id: BOOK_ID,
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

describe("the character roster", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("groups characters by tier, protagonists first", async () => {
    mockApi({
      [`/api/books/${BOOK_ID}`]: book(),
      [`/api/projects/${PROJECT_ID}/characters`]: [
        character({ id: "char-mrs-reynolds", canonical_name: "Mrs Reynolds", aliases: [], importance_tier: "minor", mention_count: 12, first_page: 200 }),
        character(),
      ],
    });

    renderRoute(`/books/${BOOK_ID}/characters`);

    await screen.findByText("Elizabeth Bennet");
    const headings = screen.getAllByRole("heading", { level: 3 }).map((node) => node.textContent);
    expect(headings.indexOf("Protagonists")).toBeLessThan(headings.indexOf("Minor"));
  });

  it("finds a character by a nickname the search box never shows", async () => {
    mockApi({
      [`/api/books/${BOOK_ID}`]: book(),
      [`/api/projects/${PROJECT_ID}/characters`]: [
        character(),
        character({ id: "char-darcy", canonical_name: "Fitzwilliam Darcy", aliases: ["Darcy", "Mr Darcy"], importance_tier: "protagonist", mention_count: 700, first_page: 15 }),
      ],
    });

    renderRoute(`/books/${BOOK_ID}/characters`);
    await screen.findByText("Fitzwilliam Darcy");

    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: /search characters/i }), "Lizzy");

    await waitFor(() => {
      expect(screen.getByText("Elizabeth Bennet")).toBeInTheDocument();
      expect(screen.queryByText("Fitzwilliam Darcy")).not.toBeInTheDocument();
    });
  });

  it("filters to a single tier and back", async () => {
    mockApi({
      [`/api/books/${BOOK_ID}`]: book(),
      [`/api/projects/${PROJECT_ID}/characters`]: [
        character(),
        character({ id: "char-footman", canonical_name: "A Footman", aliases: [], importance_tier: "mentioned", mention_count: 1, first_page: 90 }),
      ],
    });

    renderRoute(`/books/${BOOK_ID}/characters`);
    await screen.findByText("Elizabeth Bennet");
    expect(screen.getByText("A Footman")).toBeInTheDocument();

    screen.getByRole("button", { name: /^mentioned \(1\)$/i }).click();

    await waitFor(() => {
      expect(screen.queryByText("Elizabeth Bennet")).not.toBeInTheDocument();
      expect(screen.getByText("A Footman")).toBeInTheDocument();
    });
  });

  it("sorts by name", async () => {
    mockApi({
      [`/api/books/${BOOK_ID}`]: book(),
      [`/api/projects/${PROJECT_ID}/characters`]: [
        character({ id: "char-z", canonical_name: "Zeta Person", mention_count: 5, first_page: 5, aliases: [] }),
        character(),
      ],
    });

    renderRoute(`/books/${BOOK_ID}/characters`);
    await screen.findByText("Elizabeth Bennet");

    screen.getByRole("button", { name: /^name$/i }).click();

    await waitFor(() => {
      const list = screen.getByRole("list");
      const names = within(list).getAllByRole("link").map((link) => link.textContent);
      const elizabethIndex = names.findIndex((name) => name?.includes("Elizabeth"));
      const zetaIndex = names.findIndex((name) => name?.includes("Zeta"));
      expect(elizabethIndex).toBeLessThan(zetaIndex);
    });
  });

  it("shows an empty state when the roster has no characters yet", async () => {
    mockApi({
      [`/api/books/${BOOK_ID}`]: book(),
      [`/api/projects/${PROJECT_ID}/characters`]: [],
    });

    renderRoute(`/books/${BOOK_ID}/characters`);

    expect(await screen.findByText(/no characters yet/i)).toBeInTheDocument();
  });
});

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderRoute } from "./render";

const BOOK_ID = "book-1";
const PROJECT_ID = "project-1";
const CHARACTER_ID = "char-elizabeth";

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

const chapter = (overrides: Record<string, unknown> = {}) => ({
  id: "ch-1",
  book_id: BOOK_ID,
  number: 1,
  title: "Chapter One",
  page_start: 1,
  page_end: 40,
  detection_method: "regex",
  chunk_count: 5,
  ...overrides,
});

const characterDetail = (overrides: Record<string, unknown> = {}) => ({
  id: CHARACTER_ID,
  project_id: PROJECT_ID,
  canonical_name: "Elizabeth Bennet",
  aliases: ["Elizabeth", "Lizzy"],
  importance_tier: "protagonist",
  mention_count: 3,
  first_page: 3,
  first_chapter: 1,
  first_book_id: BOOK_ID,
  appears_in_books: [1],
  collision_suspected: false,
  human_verified: false,
  alias_detail: [
    { surface_form: "Elizabeth", count: 1, resolution_method: "exact", ambiguous: false },
    { surface_form: "Lizzy", count: 2, resolution_method: "nickname", ambiguous: false },
  ],
  attributes: [
    { label: "Family", value: "Second of five daughters", book_id: BOOK_ID, page: 3 },
  ],
  appearances: [],
  mentions_per_chapter: { "1": 1, "2": 2 },
  ...overrides,
});

const mention = (overrides: Record<string, unknown> = {}) => ({
  id: "mention-1",
  chunk_id: "chunk-1",
  book_id: BOOK_ID,
  surface_form: "Elizabeth",
  page: 5,
  context: "Elizabeth walked across the fields.",
  resolution_method: "exact",
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

describe("the character detail page", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows the header, aliases with their resolution method, and cited attributes", async () => {
    mockApi({
      [`/api/books/${BOOK_ID}/chapters`]: [chapter(), chapter({ id: "ch-2", number: 2, page_start: 41, page_end: 90 })],
      [`/api/books/${BOOK_ID}`]: book(),
      [`/api/characters/${CHARACTER_ID}/mentions`]: [mention()],
      [`/api/characters/${CHARACTER_ID}`]: characterDetail(),
    });

    renderRoute(`/books/${BOOK_ID}/characters/${CHARACTER_ID}`);

    expect(await screen.findByRole("heading", { name: "Elizabeth Bennet" })).toBeInTheDocument();
    expect(screen.getByText("Protagonist")).toBeInTheDocument();
    expect(screen.getByText("nickname table")).toBeInTheDocument();
    expect(screen.getByText("Second of five daughters")).toBeInTheDocument();
  });

  it("filters the mention list when a timeline bar is clicked, and clears it again", async () => {
    mockApi({
      [`/api/books/${BOOK_ID}/chapters`]: [
        chapter({ id: "ch-1", number: 1, page_start: 1, page_end: 40 }),
        chapter({ id: "ch-2", number: 2, page_start: 41, page_end: 90 }),
      ],
      [`/api/books/${BOOK_ID}`]: book(),
      [`/api/characters/${CHARACTER_ID}/mentions`]: [
        mention({ id: "m-ch1", page: 5, surface_form: "Elizabeth" }),
        mention({ id: "m-ch2-a", page: 45, surface_form: "Lizzy" }),
        mention({ id: "m-ch2-b", page: 60, surface_form: "Lizzy" }),
      ],
      [`/api/characters/${CHARACTER_ID}`]: characterDetail({ mention_count: 3 }),
    });

    renderRoute(`/books/${BOOK_ID}/characters/${CHARACTER_ID}`);
    await screen.findByRole("heading", { name: "Elizabeth Bennet" });

    // All three mentions loaded before any filter is applied.
    await waitFor(() => {
      expect(screen.getAllByText(/walked across the fields/i)).toHaveLength(3);
    });

    const chapterTwoBar = await screen.findByRole("button", { name: /chapter 2 — 2 mentions/i });
    fireEvent.click(chapterTwoBar);

    await waitFor(() => {
      expect(screen.getAllByText(/walked across the fields/i)).toHaveLength(2);
    });

    screen.getByRole("button", { name: /clear chapter filter/i }).click();

    await waitFor(() => {
      expect(screen.getAllByText(/walked across the fields/i)).toHaveLength(3);
    });
  });

  it("opens the mention inspector and shows why a form is in the cluster", async () => {
    mockApi({
      [`/api/books/${BOOK_ID}/chapters`]: [chapter()],
      [`/api/books/${BOOK_ID}`]: book(),
      [`/api/characters/${CHARACTER_ID}/mentions`]: [
        mention({ id: "m-1", surface_form: "Elizabeth", resolution_method: "exact" }),
        mention({ id: "m-2", surface_form: "Lizzy", resolution_method: "nickname" }),
      ],
      [`/api/characters/${CHARACTER_ID}`]: characterDetail(),
    });

    renderRoute(`/books/${BOOK_ID}/characters/${CHARACTER_ID}`);
    await screen.findByRole("heading", { name: "Elizabeth Bennet" });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /audit every mention/i }));

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /lizzy/i }));

    // Shown once on the group header and again on the individual mention —
    // S3.12 asks for the resolution method per mention, not just per alias.
    expect(within(dialog).getAllByText(/nickname table/i).length).toBeGreaterThanOrEqual(2);
    expect(within(dialog).getByRole("link", { name: /page 5 of pride and prejudice/i })).toBeInTheDocument();
  });
});

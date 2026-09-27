import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderRoute } from "./render";

const PROJECT_ID = "project-1";
const BOOK_1 = "book-1";
const BOOK_2 = "book-2";
const CHARACTER_ID = "char-anne";

const project = (overrides: Record<string, unknown> = {}) => ({
  id: PROJECT_ID,
  name: "Anne of Green Gables",
  slug: "anne-of-green-gables",
  kind: "series",
  book_count: 2,
  character_count: 2,
  relation_count: 1,
  updated_at: "2026-09-01T00:00:00Z",
  books: [
    { id: BOOK_1, project_id: PROJECT_ID, series_order: 1, title: "Anne of Green Gables", author: "L. M. Montgomery", page_count: 245, chapter_count: 2, character_count: 2, status: "ready", ingested_at: "2026-09-01T00:00:00Z" },
    { id: BOOK_2, project_id: PROJECT_ID, series_order: 2, title: "Anne of Avonlea", author: "L. M. Montgomery", page_count: 200, chapter_count: 1, character_count: 1, status: "ready", ingested_at: "2026-09-01T00:00:00Z" },
  ],
  ...overrides,
});

const chapter = (overrides: Record<string, unknown> = {}) => ({
  id: "ch-1",
  book_id: BOOK_1,
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
  canonical_name: "Anne Shirley",
  aliases: ["Anne", "Carrots"],
  importance_tier: "protagonist",
  mention_count: 3,
  first_page: 3,
  first_chapter: 1,
  first_book_id: BOOK_1,
  appears_in_books: [1, 2],
  collision_suspected: false,
  human_verified: false,
  alias_detail: [
    { surface_form: "Anne", count: 1, resolution_method: "exact", ambiguous: false },
    { surface_form: "Carrots", count: 2, resolution_method: "nickname", ambiguous: false },
  ],
  attributes: [
    { label: "Hair", value: "Red", book_id: BOOK_1, page: 3 },
  ],
  appearances: [
    { book_id: BOOK_1, series_order: 1, book_title: "Anne of Green Gables", first_page: 3, first_chapter: 1, mention_count: 900, importance_tier: "protagonist", surface_forms: ["Anne", "Carrots"] },
    { book_id: BOOK_2, series_order: 2, book_title: "Anne of Avonlea", first_page: 2, first_chapter: 1, mention_count: 242, importance_tier: "protagonist", surface_forms: ["Miss Shirley"] },
  ],
  mentions_per_chapter: { "1": 1, "2": 2 },
  ...overrides,
});

const mention = (overrides: Record<string, unknown> = {}) => ({
  id: "mention-1",
  chunk_id: "chunk-1",
  book_id: BOOK_1,
  surface_form: "Anne",
  page: 5,
  context: "Anne walked across the fields.",
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
      [`/api/books/${BOOK_1}/chapters`]: [chapter(), chapter({ id: "ch-2", number: 2, page_start: 41, page_end: 90 })],
      [`/api/projects/${PROJECT_ID}`]: project(),
      [`/api/characters/${CHARACTER_ID}/mentions`]: [mention()],
      [`/api/characters/${CHARACTER_ID}`]: characterDetail(),
    });

    renderRoute(`/projects/${PROJECT_ID}/characters/${CHARACTER_ID}`);

    expect(await screen.findByRole("heading", { name: "Anne Shirley" })).toBeInTheDocument();
    expect(screen.getAllByText("Protagonist").length).toBeGreaterThan(0);
    expect(screen.getByText("nickname table")).toBeInTheDocument();
    expect(screen.getByText("Red")).toBeInTheDocument();
  });

  it("lists a per-book appearance with first page, tier, mentions, and aliases for that book", async () => {
    mockApi({
      [`/api/books/${BOOK_1}/chapters`]: [chapter()],
      [`/api/projects/${PROJECT_ID}`]: project(),
      [`/api/characters/${CHARACTER_ID}/mentions`]: [mention()],
      [`/api/characters/${CHARACTER_ID}`]: characterDetail(),
    });

    renderRoute(`/projects/${PROJECT_ID}/characters/${CHARACTER_ID}`);
    await screen.findByRole("heading", { name: "Anne Shirley" });

    const appearances = screen.getByText("Appearances").closest("section") as HTMLElement;
    expect(within(appearances).getByRole("link", { name: /^1\. anne of green gables$/i })).toBeInTheDocument();
    expect(within(appearances).getByRole("link", { name: /^2\. anne of avonlea$/i })).toBeInTheDocument();
    expect(within(appearances).getByText(/miss shirley/i)).toBeInTheDocument();
    expect(within(appearances).getByText(/242 mentions/i)).toBeInTheDocument();
  });

  it("filters the mention list when a timeline bar is clicked, and clears it again", async () => {
    mockApi({
      [`/api/books/${BOOK_1}/chapters`]: [
        chapter({ id: "ch-1", number: 1, page_start: 1, page_end: 40 }),
        chapter({ id: "ch-2", number: 2, page_start: 41, page_end: 90 }),
      ],
      [`/api/projects/${PROJECT_ID}`]: project(),
      [`/api/characters/${CHARACTER_ID}/mentions`]: [
        mention({ id: "m-ch1", page: 5, surface_form: "Anne" }),
        mention({ id: "m-ch2-a", page: 45, surface_form: "Carrots" }),
        mention({ id: "m-ch2-b", page: 60, surface_form: "Carrots" }),
      ],
      [`/api/characters/${CHARACTER_ID}`]: characterDetail({ mention_count: 3 }),
    });

    renderRoute(`/projects/${PROJECT_ID}/characters/${CHARACTER_ID}`);
    await screen.findByRole("heading", { name: "Anne Shirley" });

    // All three mentions loaded before any filter is applied (all in book 1).
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
      [`/api/books/${BOOK_1}/chapters`]: [chapter()],
      [`/api/projects/${PROJECT_ID}`]: project(),
      [`/api/characters/${CHARACTER_ID}/mentions`]: [
        mention({ id: "m-1", surface_form: "Anne", resolution_method: "exact" }),
        mention({ id: "m-2", surface_form: "Carrots", resolution_method: "nickname" }),
      ],
      [`/api/characters/${CHARACTER_ID}`]: characterDetail(),
    });

    renderRoute(`/projects/${PROJECT_ID}/characters/${CHARACTER_ID}`);
    await screen.findByRole("heading", { name: "Anne Shirley" });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /audit every mention/i }));

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /carrots/i }));

    // Shown once on the group header and again on the individual mention —
    // S3.12 asks for the resolution method per mention, not just per group.
    expect(within(dialog).getAllByText(/nickname table/i).length).toBeGreaterThanOrEqual(2);
    expect(within(dialog).getByRole("link", { name: /page 5 of anne of green gables/i })).toBeInTheDocument();
  });
});

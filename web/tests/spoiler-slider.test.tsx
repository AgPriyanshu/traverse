import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderRoute } from "./render";

const PROJECT_ID = "project-1";
const BOOK_ID = "book-1";
const STORAGE_KEY = `traverse:reading-position:${PROJECT_ID}`;

const book = (overrides: Record<string, unknown> = {}) => ({
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
  ...overrides,
});

const project = (overrides: Record<string, unknown> = {}) => ({
  id: PROJECT_ID,
  name: "Anne of Green Gables",
  slug: "anne",
  kind: "standalone",
  book_count: 1,
  character_count: 4,
  relation_count: 2,
  updated_at: null,
  books: [book()],
  ...overrides,
});

const node = (id: string, name: string) => ({
  id,
  canonical_name: name,
  importance_tier: "protagonist",
  mention_count: 100,
  first_book_order: 1,
  first_chapter: 1,
  appears_in_books: [1],
});

const edge = (id: string, source: string, target: string) => ({
  id,
  source,
  target,
  predicate: "friend_of",
  family: "social",
  confidence: 0.9,
  evidence_count: 3,
  hearsay: false,
  page_refs: [{ book_order: 1, book_id: BOOK_ID, page: 10 }],
});

// A character who only appears once the reader is well past chapter 5 — the
// spoiler-leakage assertion below is that this name never reaches the DOM at
// all once the position is scoped, not merely that it's visually hidden.
const SPOILER_NAME = "Gilbert Blythe (reconciled)";

const FULL_GRAPH = {
  nodes: [node("anne", "Anne Shirley"), node("marilla", "Marilla Cuthbert"), node("gilbert", SPOILER_NAME)],
  edges: [edge("e1", "anne", "marilla"), edge("e2", "anne", "gilbert")],
  truncated: false,
};

const SCOPED_GRAPH = {
  nodes: [node("anne", "Anne Shirley"), node("marilla", "Marilla Cuthbert")],
  edges: [edge("e1", "anne", "marilla")],
  truncated: false,
};

const FULL_ROSTER = [
  { id: "anne", project_id: PROJECT_ID, canonical_name: "Anne Shirley", aliases: [], importance_tier: "protagonist", mention_count: 500, first_page: 1, first_chapter: 1, first_book_id: BOOK_ID, appears_in_books: [1] },
  { id: "gilbert", project_id: PROJECT_ID, canonical_name: SPOILER_NAME, aliases: [], importance_tier: "protagonist", mention_count: 90, first_page: 280, first_chapter: 9, first_book_id: BOOK_ID, appears_in_books: [1] },
];

const SCOPED_ROSTER = [FULL_ROSTER[0]];

const jsonResponse = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }),
  );

const seenUrls: string[] = [];

const isScoped = (url: string): boolean => {
  const params = new URL(url, "http://localhost").searchParams;
  return params.get("limit_book_order") !== null;
};

const mockApi = () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      seenUrls.push(url);
      const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();

      if (/\/api\/projects\/[^/]+\/graph/.test(url)) {
        return jsonResponse(isScoped(url) ? SCOPED_GRAPH : FULL_GRAPH);
      }
      if (/\/api\/projects\/[^/]+\/characters/.test(url)) {
        return jsonResponse(isScoped(url) ? SCOPED_ROSTER : FULL_ROSTER);
      }
      if (/\/api\/graph\/ontology/.test(url)) {
        return jsonResponse({ predicates: [], families: [] });
      }
      if (/\/api\/projects\/[^/?]+(\?|$)/.test(url) && method === "GET") {
        return jsonResponse(project());
      }
      return jsonResponse({ detail: `unhandled in test: ${url}` }, 404);
    }),
  );
};

describe("the persistent reading-position slider (S8.6)", () => {
  beforeEach(() => {
    window.localStorage.clear();
    seenUrls.length = 0;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("defaults to caught up — the whole graph, no limit params sent", async () => {
    mockApi();
    renderRoute(`/projects/${PROJECT_ID}/graph?view=list`);

    const list = await screen.findByRole("list", { name: /relationships by character/i });
    expect(within(list).getAllByText(SPOILER_NAME).length).toBeGreaterThan(0);
    expect(screen.getByText(/caught up/i)).toBeInTheDocument();
  });

  it("a stored position hard-scopes the graph — the later character never reaches the DOM", async () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ bookOrder: 1, chapter: 5 }));
    mockApi();
    renderRoute(`/projects/${PROJECT_ID}/graph?view=list`);

    const list = await screen.findByRole("list", { name: /relationships by character/i });
    expect(within(list).queryByText(SPOILER_NAME)).not.toBeInTheDocument();
    expect(screen.queryByText(SPOILER_NAME)).not.toBeInTheDocument();
    expect(screen.getByText(/chapter 5/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(seenUrls.some((url) => /\/graph\?.*limit_chapter=5/.test(url))).toBe(true);
    });
  });

  it("the same stored position scopes the character roster too", async () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ bookOrder: 1, chapter: 5 }));
    mockApi();
    renderRoute(`/projects/${PROJECT_ID}/characters`);

    await screen.findByText("Anne Shirley");
    expect(screen.queryByText(SPOILER_NAME)).not.toBeInTheDocument();

    await waitFor(() => {
      expect(seenUrls.some((url) => /\/characters\?.*limit_chapter=5/.test(url))).toBe(true);
    });
  });

  it("dragging the slider down with the keyboard re-fetches a smaller graph and persists the new position", async () => {
    mockApi();
    renderRoute(`/projects/${PROJECT_ID}/graph?view=list`);

    const list = await screen.findByRole("list", { name: /relationships by character/i });
    expect(within(list).getAllByText(SPOILER_NAME).length).toBeGreaterThan(0);

    const slider = screen.getByRole("slider", { name: /reading position/i });
    const user = userEvent.setup();
    slider.focus();
    // The rightmost step is "caught up" (no params sent at all); one step
    // left of that is the last real chapter — still everything, but now an
    // explicit position rather than an omitted one. Five steps back from
    // "caught up" lands on chapter 6 of 10. `user.keyboard` (not a raw
    // `dispatchEvent` loop) lets React commit the controlled `value` prop
    // back to the slider between presses — a fully-controlled component
    // otherwise recomputes every rapid-fire keydown off the same stale prop.
    for (let i = 0; i < 5; i += 1) {
      await user.keyboard("{ArrowLeft}");
    }

    await waitFor(() => {
      expect(screen.queryByText(SPOILER_NAME)).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "null")).toEqual({
        bookOrder: 1,
        chapter: 6,
      });
    });
    expect(screen.getByText(/up to chapter 6/i)).toBeInTheDocument();
  });
});

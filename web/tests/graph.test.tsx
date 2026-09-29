import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { buildBoundaries, buildSegments } from "@/routes/project/graph/arc-segments";
import { filterGraph, parseFilters } from "@/routes/project/graph/graph-filters";
import { RelationArcView } from "@/routes/project/graph/relation-arc";
import { renderRoute } from "./render";
import { runAxe } from "./axe";
import { render } from "@testing-library/react";
import { DesignSystemProvider } from "@/design-system/provider";
import { MemoryRouter } from "react-router";
import type { Book } from "@/lib/api";

const PROJECT_ID = "project-1";
const BOOK_1 = "book-1";
const BOOK_2 = "book-2";
const BOOK_3 = "book-3";
const ANNE = "char-anne";
const GILBERT = "char-gilbert";
const DAVY = "char-davy";

const book = (overrides: Record<string, unknown> = {}) => ({
  id: BOOK_1,
  project_id: PROJECT_ID,
  series_order: 1,
  title: "Anne of Green Gables",
  author: "L. M. Montgomery",
  page_count: 300,
  chapter_count: 10,
  character_count: 3,
  status: "ready",
  ingested_at: null,
  ...overrides,
});

const oneBook = [book()] as unknown as Book[];
const threeBooks = [
  book(),
  book({ id: BOOK_2, series_order: 2, title: "Anne of Avonlea", chapter_count: 8 }),
  book({ id: BOOK_3, series_order: 3, title: "Anne of the Island", chapter_count: 6 }),
] as unknown as Book[];

const node = (id: string, name: string, tier = "protagonist", appearsIn: number[] = [1]) => ({
  id,
  canonical_name: name,
  importance_tier: tier,
  mention_count: 100,
  first_book_order: appearsIn[0] ?? 1,
  first_chapter: 1,
  appears_in_books: appearsIn,
});

const edge = (id: string, source: string, target: string, predicate: string, family: string, bookOrders: number[], extra = {}) => ({
  id,
  source,
  target,
  predicate,
  family,
  confidence: 0.9,
  evidence_count: 3,
  hearsay: false,
  page_refs: bookOrders.map((order) => ({ book_order: order, book_id: BOOK_1, page: 10 * order })),
  ...extra,
});

const GRAPH = {
  nodes: [
    node(ANNE, "Anne Shirley", "protagonist", [1, 2, 3]),
    node(GILBERT, "Gilbert Blythe", "protagonist", [1, 2, 3]),
    node(DAVY, "Davy Keith", "major", [3]),
  ],
  edges: [
    edge("rel-enemies", ANNE, GILBERT, "enemy_of", "adversarial", [1], { confidence: 0.4 }),
    edge("rel-rivals", ANNE, GILBERT, "rival_of", "adversarial", [1, 2]),
    edge("rel-davy", GILBERT, DAVY, "cousin_of", "kinship", [3]),
  ],
  truncated: false,
};

const state = (id: string, predicate: string, firstBook: number, firstChapter: number, lastBook: number | null, lastChapter: number | null, page: number) => ({
  id,
  subject_character_id: ANNE,
  subject_name: "Anne Shirley",
  predicate,
  object_character_id: GILBERT,
  object_name: "Gilbert Blythe",
  family: "adversarial" as const,
  confidence: 0.9,
  status: "active" as const,
  assertion_type: "narrated" as const,
  hearsay: false,
  evidence_count: 2,
  first_book_order: firstBook,
  first_chapter: firstChapter,
  last_book_order: lastBook,
  last_chapter: lastChapter,
  page_refs: [{ book_order: firstBook, book_id: BOOK_1, page }],
});

describe("arc segments", () => {
  it("renders a flat relationship as one segment through the same path (single book)", () => {
    const boundaries = buildBoundaries(oneBook);
    const segments = buildSegments([state("a", "friend_of", 1, 1, null, null, 4)], boundaries);
    expect(segments).toHaveLength(1);
    expect(segments[0]).toMatchObject({ startGlobal: 1, endGlobal: 10, openEnded: true });
  });

  it("clips a state at the next state's first chapter within one book", () => {
    const boundaries = buildBoundaries(oneBook);
    const segments = buildSegments(
      [state("a", "friend_of", 1, 1, 1, 9, 4), state("b", "estranged_from", 1, 8, null, null, 90)],
      boundaries,
    );
    expect(segments.map((s) => [s.startGlobal, s.endGlobal])).toEqual([[1, 7], [8, 10]]);
  });

  it("orders three states by where they begin", () => {
    const boundaries = buildBoundaries(oneBook);
    const segments = buildSegments(
      [state("c", "married_to", 1, 12, null, null, 3), state("a", "acquainted_with", 1, 1, 1, 4, 1), state("b", "friend_of", 1, 5, 1, 11, 2)],
      boundaries,
    );
    expect(segments.map((s) => s.state.id)).toEqual(["a", "b", "c"]);
  });

  it("spans three books: enemies (bk1) → rivals (bk1–2) → friends (bk3)", () => {
    const boundaries = buildBoundaries(threeBooks);
    const segments = buildSegments(
      [
        state("enemies", "enemy_of", 1, 1, 1, 5, 4),
        state("rivals", "rival_of", 1, 6, 2, 7, 12),
        state("friends", "friend_of", 3, 1, null, null, 20),
      ],
      boundaries,
    );
    expect(segments.map((s) => s.state.id)).toEqual(["enemies", "rivals", "friends"]);
    // Book 1 spans global 1–10, book 2 spans 11–18, book 3 spans 19–24.
    expect(segments[0]).toMatchObject({ startGlobal: 1, endGlobal: 5 });
    expect(segments[1]).toMatchObject({ startGlobal: 6, endGlobal: 17 });
    expect(segments[2]).toMatchObject({ startGlobal: 19, openEnded: true });
  });

  it("cites a page and book at every state, across volumes", () => {
    render(
      <DesignSystemProvider>
        <MemoryRouter>
          <RelationArcView
            states={[
              state("enemies", "enemy_of", 1, 1, 1, 5, 4),
              state("friends", "friend_of", 3, 1, null, null, 90),
            ]}
            books={threeBooks}
          />
        </MemoryRouter>
      </DesignSystemProvider>,
    );
    expect(screen.getByRole("link", { name: /page 4 of anne of green gables/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /page 90 of anne of the island/i })).toBeInTheDocument();
    expect(screen.getByText(/bk\. 1 — anne of green gables/i)).toBeInTheDocument();
    expect(screen.getByText(/bk\. 3 — anne of the island/i)).toBeInTheDocument();
  });

  it("renders a single-book arc through the same component with no book boundaries drawn", () => {
    render(
      <DesignSystemProvider>
        <MemoryRouter>
          <RelationArcView states={[state("a", "friend_of", 1, 1, null, null, 4)]} books={oneBook} />
        </MemoryRouter>
      </DesignSystemProvider>,
    );
    expect(screen.getByRole("link", { name: /page 4 of anne of green gables/i })).toBeInTheDocument();
    expect(screen.queryByText(/bk\. 1 —/i)).not.toBeInTheDocument();
  });
});

describe("graph filters", () => {
  it("round-trips family and confidence and drops edges below the floor", () => {
    const filters = parseFilters(new URLSearchParams("family=adversarial&conf=0.5"));
    expect(filters.families).toEqual(["adversarial"]);
    const out = filterGraph(GRAPH as never, { ...filters, families: [] });
    expect(out.edges.map((e) => e.id)).toEqual(["rel-rivals", "rel-davy"]);
  });

  it("slices the standing graph to one book — Davy only appears once the book-3 filter is on", () => {
    const filters = parseFilters(new URLSearchParams("book=3"));
    const out = filterGraph(GRAPH as never, filters);
    expect(out.nodes.map((n) => n.id)).toContain(DAVY);
    // Anne and Gilbert stay too — they appear in book 3 as well — but the
    // book-1-only slice below drops Davy.
    const bookOne = filterGraph(GRAPH as never, parseFilters(new URLSearchParams("book=1")));
    expect(bookOne.nodes.map((n) => n.id)).not.toContain(DAVY);
  });
});

const jsonResponse = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }),
  );

describe("the series graph explorer, list view", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lists relationships per character, cites the books an edge spans, and opens the evidence panel with the series arc", async () => {
    const routes: Record<string, unknown> = {
      [`/api/projects/${PROJECT_ID}`]: {
        id: PROJECT_ID, name: "Anne of Green Gables", slug: "anne", kind: "series",
        book_count: 3, character_count: 3, relation_count: 2, updated_at: null,
        books: threeBooks,
      },
      "/api/graph/ontology": { predicates: [], families: [] },
      [`/api/projects/${PROJECT_ID}/graph`]: GRAPH,
      "/api/relations/rel-rivals/evidence": [
        {
          id: "ev1", book_id: BOOK_1, book_title: "Anne of Green Gables", series_order: 1, chapter_no: 2,
          page_start: 33, page_end: 33, quote: "Anne would never speak to him again.", assertion_type: "narrated",
        },
      ],
      "/api/relations/arc": {
        subject_character_id: ANNE, object_character_id: GILBERT,
        states: [state("s1", "rival_of", 1, 6, null, null, 33)],
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = input instanceof Request ? input.url : String(input);
        const match = Object.entries(routes)
          .sort(([a], [b]) => b.length - a.length)
          .find(([path]) => url.includes(path));
        return match ? jsonResponse(match[1]) : jsonResponse({ detail: url }, 404);
      }),
    );

    renderRoute(`/projects/${PROJECT_ID}/graph?view=list`);

    const list = await screen.findByRole("list", { name: /relationships by character/i });
    expect(within(list).getAllByText("Gilbert Blythe").length).toBeGreaterThan(0);
    expect(within(list).getAllByText(/bk\. 1–2/i).length).toBeGreaterThan(0);

    const user = userEvent.setup();
    await user.click(within(list).getAllByRole("button", { name: /evidence for .*rival of/i })[0] as HTMLElement);

    await waitFor(() => {
      expect(screen.getByText("Anne would never speak to him again.")).toBeInTheDocument();
    });
    expect(screen.getAllByRole("link", { name: /page 33 of anne of green gables/i }).length).toBeGreaterThan(0);
  });

  it("has no automatically detectable accessibility violations (S9.12) — the list view is the graph's non-visual equivalent", async () => {
    const routes: Record<string, unknown> = {
      [`/api/projects/${PROJECT_ID}`]: {
        id: PROJECT_ID, name: "Anne of Green Gables", slug: "anne", kind: "series",
        book_count: 3, character_count: 3, relation_count: 2, updated_at: null,
        books: threeBooks,
      },
      "/api/graph/ontology": { predicates: [], families: [] },
      [`/api/projects/${PROJECT_ID}/graph`]: GRAPH,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = input instanceof Request ? input.url : String(input);
        const match = Object.entries(routes)
          .sort(([a], [b]) => b.length - a.length)
          .find(([path]) => url.includes(path));
        return match ? jsonResponse(match[1]) : jsonResponse({ detail: url }, 404);
      }),
    );

    const { container } = renderRoute(`/projects/${PROJECT_ID}/graph?view=list`);
    await screen.findByRole("list", { name: /relationships by character/i });

    expect(await runAxe(container)).toHaveNoViolations();
  });

  it("filters to a book from the URL and shows only characters present there", async () => {
    const routes: Record<string, unknown> = {
      [`/api/projects/${PROJECT_ID}`]: {
        id: PROJECT_ID, name: "Anne of Green Gables", slug: "anne", kind: "series",
        book_count: 3, character_count: 3, relation_count: 2, updated_at: null,
        books: threeBooks,
      },
      "/api/graph/ontology": { predicates: [], families: [] },
      [`/api/projects/${PROJECT_ID}/graph`]: GRAPH,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = input instanceof Request ? input.url : String(input);
        const match = Object.entries(routes)
          .sort(([a], [b]) => b.length - a.length)
          .find(([path]) => url.includes(path));
        return match ? jsonResponse(match[1]) : jsonResponse({ detail: url }, 404);
      }),
    );

    renderRoute(`/projects/${PROJECT_ID}/graph?view=list&book=1`);

    const list = await screen.findByRole("list", { name: /relationships by character/i });
    expect(within(list).queryByText("Davy Keith")).not.toBeInTheDocument();
  });
});

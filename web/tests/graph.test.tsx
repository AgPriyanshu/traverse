import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { buildSegments } from "@/routes/book/graph/arc-segments";
import { filterGraph, parseFilters } from "@/routes/book/graph/graph-filters";
import { RelationArcView } from "@/routes/book/graph/relation-arc";
import { renderRoute } from "./render";
import { render } from "@testing-library/react";
import { DesignSystemProvider } from "@/design-system/provider";
import { MemoryRouter } from "react-router";

const BOOK_ID = "book-1";
const PROJECT_ID = "project-1";
const ELIZABETH = "char-elizabeth";
const DARCY = "char-darcy";
const WICKHAM = "char-wickham";

const node = (id: string, name: string, tier = "protagonist") => ({
  id,
  canonical_name: name,
  importance_tier: tier,
  mention_count: 100,
  first_book_order: 1,
  first_chapter: 1,
  appears_in_books: [1],
});

const edge = (id: string, source: string, target: string, predicate: string, family: string, extra = {}) => ({
  id,
  source,
  target,
  predicate,
  family,
  confidence: 0.9,
  evidence_count: 3,
  hearsay: false,
  page_refs: [{ book_order: 1, book_id: BOOK_ID, page: 10 }],
  ...extra,
});

const GRAPH = {
  nodes: [
    node(ELIZABETH, "Elizabeth Bennet"),
    node(DARCY, "Fitzwilliam Darcy"),
    node(WICKHAM, "George Wickham", "major"),
  ],
  edges: [
    edge("rel-married", ELIZABETH, DARCY, "married_to", "romantic"),
    edge("rel-enemy", DARCY, WICKHAM, "enemy_of", "adversarial", { confidence: 0.4, hearsay: true }),
  ],
  truncated: false,
};

const CHAPTERS = [
  { id: "c1", number: 1, title: "One", page_start: 1, page_end: 20 },
  { id: "c2", number: 2, title: "Two", page_start: 21, page_end: 40 },
];

const state = (id: string, predicate: string, first: number, last: number | null, page: number) => ({
  id,
  subject_character_id: ELIZABETH,
  subject_name: "Elizabeth Bennet",
  predicate,
  object_character_id: DARCY,
  object_name: "Fitzwilliam Darcy",
  family: "social" as const,
  confidence: 0.9,
  status: "active" as const,
  assertion_type: "narrated" as const,
  hearsay: false,
  evidence_count: 2,
  first_book_order: 1,
  first_chapter: first,
  last_book_order: 1,
  last_chapter: last,
  page_refs: [{ book_order: 1, book_id: BOOK_ID, page }],
});

describe("arc segments", () => {
  it("renders a flat relationship as one segment through the same path", () => {
    const segments = buildSegments([state("a", "friend_of", 1, null, 4)], 10);
    expect(segments).toHaveLength(1);
    expect(segments[0]).toMatchObject({ start: 1, end: 10, openEnded: true });
  });

  it("clips a state at the next state's first chapter", () => {
    const segments = buildSegments(
      [state("a", "friend_of", 1, 9, 4), state("b", "estranged_from", 8, null, 90)],
      20,
    );
    expect(segments.map((s) => [s.start, s.end])).toEqual([[1, 7], [8, 20]]);
  });

  it("orders three states by where they begin", () => {
    const segments = buildSegments(
      [state("c", "married_to", 12, null, 3), state("a", "acquainted_with", 1, 4, 1), state("b", "friend_of", 5, 11, 2)],
      15,
    );
    expect(segments.map((s) => s.state.id)).toEqual(["a", "b", "c"]);
  });

  it("cites a page at every state", () => {
    render(
      <DesignSystemProvider>
        <MemoryRouter>
          <RelationArcView
            states={[state("a", "friend_of", 1, 7, 4), state("b", "estranged_from", 8, null, 90)]}
            chapterCount={20}
            bookId={BOOK_ID}
            bookTitle="Pride and Prejudice"
          />
        </MemoryRouter>
      </DesignSystemProvider>,
    );
    expect(screen.getByRole("link", { name: /page 4 of pride and prejudice/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /page 90 of pride and prejudice/i })).toBeInTheDocument();
  });
});

describe("graph filters", () => {
  it("round-trips family and confidence and drops edges below the floor", () => {
    const filters = parseFilters(new URLSearchParams("family=adversarial&conf=0.5"));
    expect(filters.families).toEqual(["adversarial"]);
    const out = filterGraph(GRAPH as never, { ...filters, families: [] }, CHAPTERS as never);
    expect(out.edges.map((e) => e.id)).toEqual(["rel-married"]);
  });

  it("filters by chapter through page refs", () => {
    const out = filterGraph(
      GRAPH as never,
      parseFilters(new URLSearchParams("from=2")),
      CHAPTERS as never,
    );
    expect(out.edges).toHaveLength(0);
  });
});

const jsonResponse = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }),
  );

describe("the graph explorer list view", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lists relationships per character and opens the evidence panel", async () => {
    const routes: Record<string, unknown> = {
      [`/api/books/${BOOK_ID}/chapters`]: CHAPTERS,
      [`/api/books/${BOOK_ID}`]: {
        id: BOOK_ID, project_id: PROJECT_ID, series_order: null, title: "Pride and Prejudice",
        author: null, translator: null, page_count: 40, chapter_count: 2, status: "ready", ingested_at: null,
      },
      "/api/graph/ontology": { predicates: [], families: [] },
      [`/api/projects/${PROJECT_ID}/graph`]: GRAPH,
      "/api/relations/rel-married/evidence": [
        {
          id: "ev1", book_id: BOOK_ID, book_title: "Pride and Prejudice", chapter_no: 2,
          page_start: 33, page_end: 33, quote: "You must allow me to tell you.", assertion_type: "dialogue", asserted_by: "Darcy",
        },
      ],
      "/api/relations/arc": { subject_character_id: ELIZABETH, object_character_id: DARCY, states: [state("s1", "married_to", 1, null, 10)] },
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

    renderRoute(`/books/${BOOK_ID}/graph?view=list`);

    const list = await screen.findByRole("list", { name: /relationships by character/i });
    expect(within(list).getAllByText("Fitzwilliam Darcy").length).toBeGreaterThan(0);

    const user = userEvent.setup();
    await user.click(within(list).getAllByRole("button", { name: /evidence for .*married to/i })[0] as HTMLElement);

    await waitFor(() => {
      expect(screen.getByText("You must allow me to tell you.")).toBeInTheDocument();
    });
    expect(screen.getByText(/said by Darcy/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /page 33 of pride and prejudice/i })).toBeInTheDocument();
  });
});

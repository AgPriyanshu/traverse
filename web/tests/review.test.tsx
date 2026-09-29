import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { expectNoAxeViolations } from "./axe";
import { renderRoute } from "./render";

const BOOK_ID = "book-1";
const PROJECT_ID = "project-1";

const book = () => ({
  id: BOOK_ID,
  project_id: PROJECT_ID,
  series_order: 1,
  title: "Wuthering Heights",
  author: "Emily Brontë",
  page_count: 300,
  chapter_count: 34,
  character_count: 8,
  status: "ready",
});

const catherineEarnshaw = {
  id: "char-catherine-earnshaw",
  project_id: PROJECT_ID,
  canonical_name: "Catherine Earnshaw",
  aliases: ["Cathy"],
  importance_tier: "protagonist",
  mention_count: 220,
  first_page: 12,
  first_book_id: BOOK_ID,
};

const catherineLinton = {
  id: "char-catherine-linton",
  project_id: PROJECT_ID,
  canonical_name: "Catherine Linton",
  aliases: [],
  importance_tier: "major",
  mention_count: 80,
  first_page: 210,
  first_book_id: BOOK_ID,
};

const mergeTask = {
  id: "task-merge",
  project_id: PROJECT_ID,
  book_id: BOOK_ID,
  task_type: "merge_characters",
  status: "open",
  priority: 90,
  created_at: "2026-09-20T10:00:00Z",
  payload: {
    task_type: "merge_characters",
    candidates: [catherineEarnshaw, catherineLinton],
    contexts: {
      [catherineEarnshaw.id]: [
        { id: "m-1", chunk_id: "c-1", book_id: BOOK_ID, surface_form: "Catherine", page: 12, context: "Catherine ran across the moor.", resolution_method: "exact" },
      ],
      [catherineLinton.id]: [
        { id: "m-2", chunk_id: "c-2", book_id: BOOK_ID, surface_form: "young Catherine", page: 210, context: "Young Catherine read by the window.", resolution_method: "nickname" },
      ],
    },
    similarity_score: 0.62,
  },
};

const confirmRelationTask = {
  id: "task-confirm-relation",
  project_id: PROJECT_ID,
  book_id: BOOK_ID,
  task_type: "confirm_relation",
  status: "open",
  priority: 50,
  created_at: "2026-09-21T10:00:00Z",
  payload: {
    task_type: "confirm_relation",
    relation: {
      id: "rel-1",
      subject_character_id: catherineEarnshaw.id,
      subject_name: "Catherine Earnshaw",
      predicate: "sibling_of",
      object_character_id: "char-hindley",
      object_name: "Hindley Earnshaw",
      family: "kinship",
      confidence: 0.91,
      status: "active",
      assertion_type: "narrated",
      hearsay: false,
      evidence_count: 1,
      first_book_order: 1,
    },
    evidence: [
      { id: "ev-1", book_id: BOOK_ID, book_title: "Wuthering Heights", page_start: 14, page_end: 14, quote: "Her brother Hindley.", assertion_type: "narrated" },
    ],
    reason: "Kinship term detected but not yet confirmed.",
  },
};

const classifyTask = {
  id: "task-classify",
  project_id: PROJECT_ID,
  book_id: BOOK_ID,
  task_type: "classify_candidate",
  status: "open",
  priority: 20,
  created_at: "2026-09-22T10:00:00Z",
  payload: {
    task_type: "classify_candidate",
    surface_form: "the Grange",
    book_id: BOOK_ID,
    kind_guess: "place",
    mention_count: 6,
    contexts: [
      { id: "m-3", chunk_id: "c-3", book_id: BOOK_ID, surface_form: "the Grange", page: 30, context: "They rode to the Grange.", resolution_method: "exact" },
    ],
  },
};

const tasks = [mergeTask, confirmRelationTask, classifyTask];

type MockOptions = {
  onResolve?: (taskId: string, body: Record<string, unknown>) => void;
};

const jsonResponse = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json" } });

const mockApi = (options: MockOptions = {}) => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();

      const resolveMatch = /\/api\/review\/tasks\/([^/]+)\/resolve$/.exec(url);
      if (method === "POST" && resolveMatch) {
        const taskId = resolveMatch[1] ?? "";
        const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        options.onResolve?.(taskId, body);
        const task = tasks.find((t) => t.id === taskId);
        return Promise.resolve(jsonResponse({ ...task, status: "resolved" }));
      }
      if (/\/api\/review\/tasks(\?|$)/.test(url)) {
        return Promise.resolve(jsonResponse(tasks));
      }
      if (/\/api\/graph\/ontology/.test(url)) {
        return Promise.resolve(jsonResponse({ predicates: [{ predicate: "sibling_of", family: "kinship" }, { predicate: "parent_of", family: "kinship" }], families: ["kinship"] }));
      }
      if (/\/api\/books\/[^/?]+(\?|$)/.test(url)) {
        return Promise.resolve(jsonResponse(book()));
      }
      return Promise.resolve(jsonResponse({ detail: `unhandled in test: ${url}` }, 404));
    }),
  );
};

describe("the review queue", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows the highest-priority task first, above lower-leverage tasks", async () => {
    mockApi();
    renderRoute(`/books/${BOOK_ID}/review`);

    expect(await screen.findByText(/task 1 of 3/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /catherine earnshaw & catherine linton/i })).toBeInTheDocument();
  });

  it("has no automatically detectable accessibility violations (S9.12)", async () => {
    mockApi();
    const { container } = renderRoute(`/books/${BOOK_ID}/review`);

    await screen.findByText(/task 1 of 3/i);

    await expectNoAxeViolations(container);
  });

  it("moves through the queue with j/k, never the mouse", async () => {
    mockApi();
    renderRoute(`/books/${BOOK_ID}/review`);

    await screen.findByText(/task 1 of 3/i);
    fireEvent.keyDown(document, { key: "j" });
    expect(await screen.findByText(/task 2 of 3/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /hindley earnshaw/i })).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "k" });
    expect(await screen.findByText(/task 1 of 3/i)).toBeInTheDocument();
  });

  it("renders the merge task as side-by-side contexts and merges with 'm'", async () => {
    const onResolve = vi.fn();
    mockApi({ onResolve });
    renderRoute(`/books/${BOOK_ID}/review`);

    await screen.findByText(/task 1 of 3/i);
    expect(screen.getByText(/catherine ran across the moor/i)).toBeInTheDocument();
    expect(screen.getByText(/young catherine read by the window/i)).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "m" });

    // Optimistic: the task leaves the queue immediately, before the undo
    // grace period has elapsed and before any request is sent.
    await waitFor(() => {
      expect(screen.getByText(/2 open/i)).toBeInTheDocument();
    });
    expect(onResolve).not.toHaveBeenCalled();
    expect(await screen.findByText(/merged into catherine earnshaw/i)).toBeInTheDocument();
  });

  it("undoes a resolution before the grace period commits it, with no request sent", async () => {
    const onResolve = vi.fn();
    mockApi({ onResolve });
    renderRoute(`/books/${BOOK_ID}/review`);

    await screen.findByText(/task 1 of 3/i);
    fireEvent.keyDown(document, { key: "m" });
    await waitFor(() => { expect(screen.getByText(/2 open/i)).toBeInTheDocument(); });

    fireEvent.keyDown(document, { key: "u" });

    await waitFor(() => { expect(screen.getByText(/3 open/i)).toBeInTheDocument(); });
    expect(onResolve).not.toHaveBeenCalled();
  });

  it("accepts a confirm_relation task with 'a' after moving to it", async () => {
    const onResolve = vi.fn();
    mockApi({ onResolve });
    renderRoute(`/books/${BOOK_ID}/review`);

    await screen.findByText(/task 1 of 3/i);
    fireEvent.keyDown(document, { key: "j" });
    await screen.findByText(/task 2 of 3/i);

    fireEvent.keyDown(document, { key: "a" });
    expect(await screen.findByText(/accepted relation/i)).toBeInTheDocument();
    expect(onResolve).not.toHaveBeenCalled();
  });

  it("classifies a candidate with a single key", async () => {
    mockApi();
    renderRoute(`/books/${BOOK_ID}/review`);

    await screen.findByText(/task 1 of 3/i);
    fireEvent.keyDown(document, { key: "j" });
    fireEvent.keyDown(document, { key: "j" });
    expect(await screen.findByText(/task 3 of 3/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /the grange/i })).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "p" });
    expect(await screen.findByText(/classified as place/i)).toBeInTheDocument();
  });

  it("opens the shortcuts legend with '?'", async () => {
    mockApi();
    renderRoute(`/books/${BOOK_ID}/review`);

    await screen.findByText(/task 1 of 3/i);
    fireEvent.keyDown(document, { key: "?" });

    const dialog = await screen.findByRole("dialog", { name: /keyboard shortcuts/i });
    expect(within(dialog).getByText(/next task/i)).toBeInTheDocument();
  });

  it("bulk-accepts selected tasks together", async () => {
    const onResolve = vi.fn();
    mockApi({ onResolve });
    renderRoute(`/books/${BOOK_ID}/review`);

    await screen.findByText(/task 1 of 3/i);

    const selectButtons = screen.getAllByRole("button", { name: /select for bulk accept/i });
    fireEvent.click(selectButtons[1] as HTMLElement); // confirm_relation task
    fireEvent.click(selectButtons[2] as HTMLElement); // classify_candidate task

    // Both selected tasks bulk-accept cleanly on their own (confirm_relation
    // always can; classify_candidate can because it carries a `kind_guess`).
    const acceptButton = await screen.findByRole("button", { name: /^accept 2$/i });
    fireEvent.click(acceptButton);

    expect(await screen.findByText(/accepted 2/i)).toBeInTheDocument();
    expect(onResolve).not.toHaveBeenCalled();
  });
});

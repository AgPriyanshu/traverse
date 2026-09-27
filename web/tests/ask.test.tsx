import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resetConversations } from "@/routes/ask/conversation-store";
import { renderRoute } from "./render";

const BOOK_ID = "book-1";
const PROJECT_ID = "project-1";

const book = (overrides: Record<string, unknown> = {}) => ({
  id: BOOK_ID,
  project_id: PROJECT_ID,
  series_order: 1,
  title: "Pride and Prejudice",
  author: "Jane Austen",
  page_count: 400,
  chapter_count: 61,
  character_count: 12,
  status: "ready",
  ...overrides,
});

const project = (overrides: Record<string, unknown> = {}) => ({
  id: PROJECT_ID,
  name: "Pride and Prejudice",
  slug: "pride-and-prejudice",
  kind: "standalone",
  book_count: 1,
  character_count: 2,
  relation_count: 1,
  books: [book()],
  ...overrides,
});

const characters = [
  { id: "c-1", project_id: PROJECT_ID, canonical_name: "Elizabeth Bennet", aliases: ["Lizzy"], importance_tier: "protagonist", mention_count: 900, appears_in_books: [1] },
  { id: "c-2", project_id: PROJECT_ID, canonical_name: "Mr Darcy", aliases: [], importance_tier: "protagonist", mention_count: 700, appears_in_books: [1] },
];

const pageRender = (page: number) => ({
  book_id: BOOK_ID,
  page,
  image_url: `https://cdn.example.com/${BOOK_ID}/pages/${page}.png`,
  width: 612,
  height: 792,
  spans: [],
});

const sseBody = (frames: string[]) =>
  new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const frame of frames) { controller.enqueue(encoder.encode(frame)); }
      controller.close();
    },
  });

const sseResponse = (frames: string[]) =>
  new Response(sseBody(frames), {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });

const jsonResponse = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });

const frame = (event: Record<string, unknown>) => `data: ${JSON.stringify(event)}\n\n`;

const ANSWER_FRAMES = [
  frame({ type: "route", route: "character_lookup", explanation: "asks about one character" }),
  frame({ type: "token", text: "Elizabeth Bennet is the second " }),
  frame({ type: "token", text: "of five daughters." }),
  frame({
    type: "citation",
    index: 0,
    citation: { book_id: BOOK_ID, book_title: "Pride and Prejudice", page_start: 12, page_end: 12 },
  }),
  frame({ type: "done", thread_id: "thread-1", citation_count: 1, latency_ms: 900, abstained: false }),
];

const ABSTAIN_FRAMES = [
  frame({ type: "token", text: "Elizabeth has no brother in this novel." }),
  frame({ type: "done", thread_id: "thread-2", citation_count: 0, abstained: true }),
];

const INTERRUPT_FRAMES = [
  frame({
    type: "interrupt",
    thread_id: "thread-3",
    question: "Which Catherine do you mean?",
    options: ["Catherine de Bourgh", "Catherine Morland"],
  }),
];

const RESUME_FRAMES = [
  frame({ type: "token", text: "Lady Catherine de Bourgh is Mr Darcy's aunt." }),
  frame({ type: "done", thread_id: "thread-3", citation_count: 0, abstained: false }),
];

type MockOptions = {
  onQuery?: (body: Record<string, unknown>) => string[];
  onRespond?: (threadId: string, body: Record<string, unknown>) => string[];
};

const mockApi = (options: MockOptions = {}) => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();

      if (method === "POST" && /\/api\/query\/[^/]+\/respond$/.test(url)) {
        const threadId = /\/api\/query\/([^/]+)\/respond$/.exec(url)?.[1] ?? "";
        const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        const frames = options.onRespond?.(threadId, body) ?? [];
        return Promise.resolve(sseResponse(frames));
      }
      if (method === "POST" && /\/api\/query$/.test(url)) {
        const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        const frames = options.onQuery?.(body) ?? [];
        return Promise.resolve(sseResponse(frames));
      }

      const pageMatch = /\/api\/books\/[^/]+\/pages\/(\d+)/.exec(url);
      if (pageMatch) {
        return Promise.resolve(jsonResponse(pageRender(Number(pageMatch[1]))));
      }
      if (/\/api\/projects\/[^/]+\/characters/.test(url)) {
        return Promise.resolve(jsonResponse(characters));
      }
      if (/\/api\/projects\/[^/?]+(\?|$)/.test(url)) {
        return Promise.resolve(jsonResponse(project()));
      }
      if (/\/api\/books\/[^/?]+(\?|$)/.test(url)) {
        return Promise.resolve(jsonResponse(book()));
      }
      return Promise.resolve(jsonResponse({ detail: `unhandled in test: ${url}` }, 404));
    }),
  );
};

describe("the ask screen", () => {
  // Cleared before, not after: `@testing-library/react`'s own `afterEach(cleanup)`
  // is registered at file scope (on import) while this hook is registered
  // inside `describe`, so it runs *before* that cleanup unmounts the
  // component — resetting here would just be repopulated by the unmount
  // effect a moment later. Every test starting from a clean store is what
  // actually matters, so `beforeEach` sidesteps the ordering.
  beforeEach(() => {
    resetConversations();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows suggested questions derived from the roster on landing", async () => {
    mockApi();
    renderRoute(`/books/${BOOK_ID}/ask`);

    expect(
      await screen.findByRole("button", { name: /who is elizabeth bennet/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /how does elizabeth bennet know mr darcy/i }),
    ).toBeInTheDocument();
  });

  it("streams tokens and renders an inline, clickable citation with its own claim", async () => {
    mockApi({ onQuery: () => ANSWER_FRAMES });
    renderRoute(`/books/${BOOK_ID}/ask`);

    fireEvent.click(await screen.findByRole("button", { name: /who is elizabeth bennet/i }));

    const answer = await screen.findByTestId("answer-text");
    await waitFor(() => {
      expect(within(answer).getByText(/second/)).toBeInTheDocument();
      expect(within(answer).getByText(/five daughters/)).toBeInTheDocument();
    });

    const citation = within(answer).getByRole("link");
    expect(citation).toHaveAttribute("href", `/books/${BOOK_ID}/pages/12`);
    expect(citation).toHaveAccessibleName(/citation 0.*page 12 of pride and prejudice/i);

    // The route decision is shown, subtly (S6.10).
    expect(await screen.findByText(/answered from the character record/i)).toBeInTheDocument();
  });

  it("renders an abstention as a considered answer, not an error", async () => {
    mockApi({ onQuery: () => ABSTAIN_FRAMES });
    renderRoute(`/books/${BOOK_ID}/ask`);

    fireEvent.click(await screen.findByRole("button", { name: /who is elizabeth bennet/i }));

    expect(await screen.findByText(/no brother in this novel/i)).toBeInTheDocument();
    expect(screen.getByText(/not established in the text/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("presents a clarifying interrupt and resumes the stream on an answer", async () => {
    mockApi({
      onQuery: () => INTERRUPT_FRAMES,
      onRespond: () => RESUME_FRAMES,
    });
    renderRoute(`/books/${BOOK_ID}/ask`);

    fireEvent.click(await screen.findByRole("button", { name: /who is elizabeth bennet/i }));

    expect(await screen.findByText(/which catherine do you mean/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /catherine de bourgh/i }));

    expect(await screen.findByText(/mr darcy's aunt/i)).toBeInTheDocument();
    expect(screen.queryByText(/which catherine do you mean/i)).not.toBeInTheDocument();
  });

  it("carries the thread across a follow-up turn and keeps both in the conversation", async () => {
    const threadIds: unknown[] = [];
    mockApi({
      onQuery: (body) => {
        threadIds.push(body.thread_id);
        return ANSWER_FRAMES;
      },
    });
    renderRoute(`/books/${BOOK_ID}/ask`);

    fireEvent.click(await screen.findByRole("button", { name: /who is elizabeth bennet/i }));
    await screen.findByText(/answered from the character record/i);
    expect(threadIds).toEqual([null]);

    const input = screen.getByRole("textbox", { name: /ask a question/i });
    fireEvent.change(input, { target: { value: "And her sister?" } });
    fireEvent.click(screen.getByRole("button", { name: /^ask$/i }));

    await waitFor(() => { expect(threadIds).toEqual([null, "thread-1"]); });
    expect(screen.getAllByText(/five daughters/i)).toHaveLength(2);
  });

  it("preserves the conversation when a citation is followed to its page and back", async () => {
    mockApi({ onQuery: () => ANSWER_FRAMES });
    const { router } = renderRoute(`/books/${BOOK_ID}/ask`);

    fireEvent.click(await screen.findByRole("button", { name: /who is elizabeth bennet/i }));
    const answer = await screen.findByTestId("answer-text");
    await waitFor(() => {
      expect(within(answer).getByText(/five daughters/)).toBeInTheDocument();
    });

    fireEvent.click(within(answer).getByRole("link"));
    expect(await screen.findByText(/page 12/i)).toBeInTheDocument();

    await router.navigate(-1);

    // The whole turn — question, prose and citation — is back, not reset,
    // and the thread continues rather than starting a fresh conversation
    // (S6.11: "get back to the answer without losing it").
    expect(await screen.findByTestId("answer-text")).toBeInTheDocument();
    expect(screen.getByText(/who is elizabeth bennet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /citation 0/i })).toHaveAttribute(
      "href",
      `/books/${BOOK_ID}/pages/12`,
    );
  });

  it("shows the book's reading-position scope with a way to clear it", async () => {
    mockApi();
    renderRoute(`/books/${BOOK_ID}/ask`);

    expect(await screen.findByText(/asking about pride and prejudice/i)).toBeInTheDocument();
    const clear = screen.getByRole("link", { name: /ask the whole series instead/i });
    expect(clear).toHaveAttribute("href", `/projects/${PROJECT_ID}/ask`);
  });
});

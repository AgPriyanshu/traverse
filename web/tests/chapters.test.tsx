import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderRoute } from "./render";

const BOOK_ID = "abc-123";

const chapter = (overrides: Record<string, unknown> = {}) => ({
  id: "ch-1",
  book_id: BOOK_ID,
  number: 3,
  title: "The Ball at Netherfield",
  page_start: 40,
  page_end: 58,
  detection_method: "llm",
  chunk_count: 2,
  ...overrides,
});

const chunk = (overrides: Record<string, unknown> = {}) => ({
  id: "chunk-1",
  book_id: BOOK_ID,
  chapter_id: "ch-1",
  chapter_number: 3,
  text: "Elizabeth danced with Mr Darcy, though neither much enjoyed it.",
  pages: [42],
  page_start: 42,
  page_end: 42,
  token_count: 128,
  dense_score: null,
  lexical_score: null,
  ...overrides,
});

const jsonResponse = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );

describe("the chapters screen", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("lists a chapter with its page range and detection method", async () => {
    mockApi({
      [`/api/books/${BOOK_ID}/chapters`]: [chapter()],
      [`/api/books/${BOOK_ID}/chunks`]: [],
    });

    renderRoute(`/books/${BOOK_ID}/chapters`);

    expect(
      await screen.findByText(/chapter 3 · the ball at netherfield/i),
    ).toBeInTheDocument();
    expect(screen.getByText("llm")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /2 chunks/i })).toBeInTheDocument();
  });

  it("opens the chunk drawer, showing text, page ref and token count", async () => {
    mockApi({
      [`/api/books/${BOOK_ID}/chapters`]: [chapter()],
      [`/api/books/${BOOK_ID}/chunks`]: [
        chunk(),
        chunk({ id: "chunk-2", chapter_id: "other-chapter" }),
      ],
    });

    renderRoute(`/books/${BOOK_ID}/chapters`);
    (await screen.findByRole("button", { name: /2 chunks/i })).click();

    expect(
      await screen.findByText(/elizabeth danced with mr darcy/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/128 tokens/i)).toBeInTheDocument();
    // Only the matching chapter's chunk shows — the other chapter's is filtered out.
    expect(screen.queryAllByText(/elizabeth danced/i)).toHaveLength(1);
  });

  it("shows retrieval scores only when a chunk actually carries them", async () => {
    mockApi({
      [`/api/books/${BOOK_ID}/chapters`]: [chapter({ chunk_count: 1 })],
      [`/api/books/${BOOK_ID}/chunks`]: [
        chunk({ dense_score: 0.812_345, lexical_score: 0.5 }),
      ],
    });

    renderRoute(`/books/${BOOK_ID}/chapters`);
    (await screen.findByRole("button", { name: /1 chunk\b/i })).click();

    expect(await screen.findByText(/dense 0\.812/)).toBeInTheDocument();
    expect(screen.getByText(/lexical 0\.500/)).toBeInTheDocument();
  });

  it("closes the drawer from its close button", async () => {
    mockApi({
      [`/api/books/${BOOK_ID}/chapters`]: [chapter({ chunk_count: 1 })],
      [`/api/books/${BOOK_ID}/chunks`]: [chunk()],
    });

    renderRoute(`/books/${BOOK_ID}/chapters`);
    (await screen.findByRole("button", { name: /1 chunk\b/i })).click();
    await screen.findByText(/elizabeth danced with mr darcy/i);

    screen.getByRole("button", { name: /^close$/i }).click();

    await waitFor(() => {
      expect(
        screen.queryByText(/elizabeth danced with mr darcy/i),
      ).not.toBeInTheDocument();
    });
  });
});

function mockApi(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      // `openapi-fetch` calls the configured `fetch` with a `Request`
      // instance, not a bare URL string — `String(request)` stringifies to
      // "[object Request]", so the real URL has to come off `.url`.
      const url = input instanceof Request ? input.url : String(input);
      const match = Object.entries(routes).find(([path]) => url.includes(path));
      if (match) { return jsonResponse(match[1]); }
      return jsonResponse({ detail: `unhandled in test: ${url}` }, 404);
    }),
  );
}

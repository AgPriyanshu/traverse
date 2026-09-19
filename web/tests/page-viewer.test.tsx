import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderRoute } from "./render";

const BOOK_ID = "abc-123";

const book = (overrides: Record<string, unknown> = {}) => ({
  id: BOOK_ID,
  project_id: "p-1",
  title: "Pride and Prejudice",
  author: "Jane Austen",
  page_count: 20,
  chapter_count: 61,
  character_count: 12,
  status: "ready",
  ...overrides,
});

const pageRender = (page: number, overrides: Record<string, unknown> = {}) => ({
  book_id: BOOK_ID,
  page,
  image_url: `https://cdn.example.com/${BOOK_ID}/pages/${page}.png`,
  width: 612,
  height: 792,
  spans: [],
  ...overrides,
});

const jsonResponse = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );

/**
 * Routed on the URL shape rather than `String.includes` — `/pages/5` is a
 * substring match away from colliding with `/api/books/{id}` itself, so the
 * more specific pattern has to be checked first.
 */
const mockApi = ({
  book: bookFixture,
  pages = {},
}: {
  book?: Record<string, unknown>;
  pages?: Record<number, Record<string, unknown> | undefined>;
}) => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = input instanceof Request ? input.url : String(input);
      const pageMatch = /\/api\/books\/[^/]+\/pages\/(\d+)/.exec(url);
      if (pageMatch) {
        const data = pages[Number(pageMatch[1])];
        return data
          ? jsonResponse(data)
          : jsonResponse({ detail: "page not found" }, 404);
      }
      if (/\/api\/books\/[^/?]+(\?|$)/.test(url)) {
        return bookFixture
          ? jsonResponse(bookFixture)
          : jsonResponse({ detail: "book not found" }, 404);
      }
      return jsonResponse({ detail: `unhandled in test: ${url}` }, 404);
    }),
  );
};

describe("the page viewer", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders the page image, its span count, and a page heading", async () => {
    mockApi({
      book: book(),
      pages: { 5: pageRender(5, { spans: [{}, {}, {}] }) },
    });

    renderRoute(`/books/${BOOK_ID}/pages/5`);

    expect(
      await screen.findByRole("heading", { name: /page 5/i }),
    ).toBeInTheDocument();
    const image = await screen.findByRole("img", { name: /page 5/i });
    expect(image).toHaveAttribute(
      "src",
      `https://cdn.example.com/${BOOK_ID}/pages/5.png`,
    );
    expect(screen.getByText(/3 text spans/i)).toBeInTheDocument();
  });

  it("advances to the next page and back with the toolbar buttons", async () => {
    mockApi({
      book: book(),
      pages: { 5: pageRender(5), 6: pageRender(6) },
    });

    renderRoute(`/books/${BOOK_ID}/pages/5`);
    await screen.findByRole("heading", { name: /page 5/i });

    fireEvent.click(screen.getByRole("button", { name: /next page/i }));
    expect(
      await screen.findByRole("heading", { name: /page 6/i }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /previous page/i }));
    expect(
      await screen.findByRole("heading", { name: /page 5/i }),
    ).toBeInTheDocument();
  });

  it("navigates with the arrow keys", async () => {
    mockApi({
      book: book(),
      pages: { 5: pageRender(5), 6: pageRender(6) },
    });

    renderRoute(`/books/${BOOK_ID}/pages/5`);
    await screen.findByRole("heading", { name: /page 5/i });

    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(
      await screen.findByRole("heading", { name: /page 6/i }),
    ).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(
      await screen.findByRole("heading", { name: /page 5/i }),
    ).toBeInTheDocument();
  });

  it("disables Previous on the first page and Next on the last page", async () => {
    mockApi({
      book: book({ page_count: 5 }),
      pages: { 5: pageRender(5) },
    });

    renderRoute(`/books/${BOOK_ID}/pages/5`);
    await screen.findByRole("heading", { name: /page 5/i });
    // Waits for the book's page_count (a second, independent query) to land
    // — until then "Next" has nothing to clamp against and stays enabled.
    await screen.findByText(/of 5/i);

    expect(screen.getByRole("button", { name: /next page/i })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /previous page/i }),
    ).not.toBeDisabled();
  });

  it("jumps to a typed page number", async () => {
    mockApi({
      book: book(),
      pages: { 5: pageRender(5), 11: pageRender(11) },
    });

    renderRoute(`/books/${BOOK_ID}/pages/5`);
    await screen.findByRole("heading", { name: /page 5/i });

    const input = screen.getByLabelText(/page/i, { selector: "input" });
    fireEvent.change(input, { target: { value: "11" } });
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    expect(
      await screen.findByRole("heading", { name: /page 11/i }),
    ).toBeInTheDocument();
  });

  it("switches zoom modes", async () => {
    mockApi({ book: book(), pages: { 5: pageRender(5) } });

    renderRoute(`/books/${BOOK_ID}/pages/5`);
    await screen.findByRole("heading", { name: /page 5/i });

    const fitWidth = screen.getByRole("button", { name: /fit width/i });
    const hundred = screen.getByRole("button", { name: /^100%$/i });
    expect(fitWidth).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(hundred);
    expect(hundred).toHaveAttribute("aria-pressed", "true");
    expect(fitWidth).toHaveAttribute("aria-pressed", "false");
  });

  it("renders a highlight from the ?highlight= search param", async () => {
    mockApi({ book: book(), pages: { 5: pageRender(5) } });

    const { container } = renderRoute(
      `/books/${BOOK_ID}/pages/5?highlight=100,200,50,20`,
    );
    await screen.findByRole("heading", { name: /page 5/i });

    await waitFor(() => {
      expect(
        container.querySelectorAll('[data-highlight-kind="citation"]'),
      ).toHaveLength(1);
    });
  });

  it("ignores a malformed highlight rather than crashing", async () => {
    mockApi({ book: book(), pages: { 5: pageRender(5) } });

    const { container } = renderRoute(
      `/books/${BOOK_ID}/pages/5?highlight=not-a-number`,
    );
    await screen.findByRole("heading", { name: /page 5/i });

    expect(container.querySelectorAll("[data-highlight-kind]")).toHaveLength(0);
  });

  it("shows an invalid-page error rather than calling the API with garbage", async () => {
    mockApi({ book: book(), pages: {} });

    renderRoute(`/books/${BOOK_ID}/pages/not-a-page`);

    expect(
      await screen.findByRole("heading", { name: /invalid page/i }),
    ).toBeInTheDocument();
  });
});

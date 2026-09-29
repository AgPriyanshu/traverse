import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { expectNoAxeViolations } from "./axe";
import { renderRoute } from "./render";

const jsonResponse = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );

const project = (overrides: Record<string, unknown> = {}) => ({
  id: "p-1",
  name: "Pride and Prejudice Demo",
  slug: "pride-and-prejudice-demo",
  kind: "standalone",
  book_count: 1,
  character_count: 3,
  relation_count: 2,
  updated_at: "2026-09-01T00:00:00Z",
  ...overrides,
});

const characters = [
  { id: "c-1", project_id: "p-1", canonical_name: "Elizabeth Bennet", aliases: ["Lizzy"], importance_tier: "protagonist", mention_count: 900, appears_in_books: [1] },
  { id: "c-2", project_id: "p-1", canonical_name: "Mr Darcy", aliases: [], importance_tier: "protagonist", mention_count: 700, appears_in_books: [1] },
];

function mockApi(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes("/api/health")) {
        return jsonResponse({ status: "ok", dependencies: [] });
      }
      const match = Object.entries(routes)
        .sort(([a], [b]) => b.length - a.length)
        .find(([path]) => url.includes(path));
      if (match) { return jsonResponse(match[1]); }
      return jsonResponse({ detail: `unhandled in test: ${url}` }, 404);
    }),
  );
}

/**
 * PRD §9.1 — public landing state. No signup gate exists in this app (the
 * whole product has none), so "public" here means: the root route is a
 * read-only demo entry point, not the internal library, and a skimming
 * visitor reaches a cited answer in one click.
 */
describe("the public landing screen", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("features the seeded Pride and Prejudice project over an unrelated one, read-only", async () => {
    mockApi({
      "/api/projects": [
        project({ id: "p-other", name: "Some Other Novel", slug: "some-other-novel", character_count: 40 }),
        project(),
      ],
      "/api/projects/p-1/characters": characters,
    });

    renderRoute("/");

    expect(await screen.findByRole("heading", { name: "Pride and Prejudice Demo" })).toBeInTheDocument();
    expect(screen.getByText(/read-only demo/i)).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: /who is elizabeth bennet/i }),
    ).toBeInTheDocument();
  });

  it("sends a suggested question straight into a cited-answer conversation", async () => {
    const user = userEvent.setup();
    mockApi({
      "/api/projects": [project()],
      "/api/projects/p-1/characters": characters,
      "/api/projects/p-1": project(),
      "/api/query": { detail: "not stubbed for this test" },
    });

    renderRoute("/");

    const question = await screen.findByRole("button", { name: /who is elizabeth bennet/i });
    await user.click(question);

    expect(await screen.findByRole("heading", { name: /ask about pride and prejudice demo/i })).toBeInTheDocument();
  });

  it("shows an upload onboarding state, never a blank page, when no project exists yet", async () => {
    mockApi({ "/api/projects": [] });

    renderRoute("/");

    expect(
      await screen.findByRole("heading", { name: /upload a book to see traverse work/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /upload your first book/i })).toHaveAttribute("href", "/books/upload");
  });

  it("states the upload sandbox's quota up front, not on rejection", async () => {
    mockApi({ "/api/projects": [project()], "/api/projects/p-1/characters": characters });

    renderRoute("/");

    expect(
      await screen.findByText(/one pdf, up to 150 pages, and deletes it automatically after 24 hours/i),
    ).toBeInTheDocument();
  });

  it("has no automatically detectable accessibility violations (S9.12)", async () => {
    mockApi({ "/api/projects": [project()], "/api/projects/p-1/characters": characters });

    const { container } = renderRoute("/");
    await screen.findByRole("heading", { name: "Pride and Prejudice Demo" });

    await expectNoAxeViolations(container);
  });
});

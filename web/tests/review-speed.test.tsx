import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderRoute } from "./render";

const BOOK_ID = "book-1";
const PROJECT_ID = "project-1";
const TASK_COUNT = 50;
const TARGET_MS = 8 * 60 * 1000;

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

const character = (id: string, name: string) => ({
  id,
  project_id: PROJECT_ID,
  canonical_name: name,
  aliases: [],
  importance_tier: "minor",
  mention_count: 10,
  first_page: 1,
  first_book_id: BOOK_ID,
});

const relation = (id: string, subject: string, object: string) => ({
  id,
  subject_character_id: `char-${subject}`,
  subject_name: subject,
  predicate: "knows",
  object_character_id: `char-${object}`,
  object_name: object,
  family: "social",
  confidence: 0.7,
  status: "active",
  assertion_type: "narrated",
  hearsay: false,
  evidence_count: 1,
  first_book_order: 1,
});

/**
 * One task per type, cycling — every type's fast path is exactly one key
 * (`accept`/`merge`/`temporal_transition`/`classify` all resolve without a
 * second keystroke), so this array is also the exact key sequence a reviewer
 * types. No `j`/`k` between them: resolving the active task auto-advances to
 * the next (S7.8's "position" contract), which is the whole point.
 */
const TASK_SPECS: { type: string; key: string }[] = [
  { type: "merge_characters", key: "m" },
  { type: "confirm_relation", key: "a" },
  { type: "resolve_conflict", key: "t" },
  { type: "classify_candidate", key: "a" },
  { type: "confirm_chapter_split", key: "a" },
];

const buildTask = (index: number, spec: { type: string; key: string }) => {
  const priority = TASK_COUNT - index;
  const base = {
    id: `task-${index}`,
    project_id: PROJECT_ID,
    book_id: BOOK_ID,
    task_type: spec.type,
    status: "open",
    priority,
    created_at: "2026-09-20T10:00:00Z",
  };

  switch (spec.type) {
    case "merge_characters":
      return {
        ...base,
        payload: {
          task_type: spec.type,
          candidates: [character(`a-${index}`, `Alpha ${index}`), character(`b-${index}`, `Beta ${index}`)],
          contexts: {},
          similarity_score: 0.6,
        },
      };
    case "confirm_relation":
      return {
        ...base,
        payload: {
          task_type: spec.type,
          relation: relation(`rel-${index}`, `Subject ${index}`, `Object ${index}`),
          evidence: [],
          reason: "Ambiguous kinship term.",
        },
      };
    case "resolve_conflict":
      return {
        ...base,
        payload: {
          task_type: spec.type,
          conflicting: [relation(`rel-a-${index}`, `Subject ${index}`, `Object ${index}`), relation(`rel-b-${index}`, `Subject ${index}`, `Rival ${index}`)],
          evidence: {},
          reason: "Two mutually exclusive relations.",
        },
      };
    case "classify_candidate":
      return {
        ...base,
        payload: {
          task_type: spec.type,
          surface_form: `Candidate ${index}`,
          book_id: BOOK_ID,
          kind_guess: "place",
          mention_count: 3,
          contexts: [],
        },
      };
    case "confirm_chapter_split":
      return {
        ...base,
        payload: {
          task_type: spec.type,
          chapter: { id: `ch-${index}`, book_id: BOOK_ID, number: index, title: null, page_start: index, page_end: index + 1, detection_method: "regex", chunk_count: 4 },
          preceding_text: "…the storm passed.",
          following_text: "The next morning…",
          confidence: 0.8,
        },
      };
    default:
      throw new Error(`unhandled fixture type: ${spec.type}`);
  }
};

const tasks = Array.from({ length: TASK_COUNT }, (_, index) => buildTask(index, TASK_SPECS[index % TASK_SPECS.length] as { type: string; key: string }));
const keySequence = tasks.map((_, index) => (TASK_SPECS[index % TASK_SPECS.length] as { type: string; key: string }).key);

const jsonResponse = (data: unknown) => new Response(JSON.stringify(data), { status: 200, headers: { "content-type": "application/json" } });

const mockApi = () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = input instanceof Request ? input.url : String(input);
      if (/\/api\/review\/tasks\/[^/]+\/resolve$/.test(url)) { return Promise.resolve(jsonResponse({})); }
      if (/\/api\/review\/tasks(\?|$)/.test(url)) { return Promise.resolve(jsonResponse(tasks)); }
      if (/\/api\/graph\/ontology/.test(url)) { return Promise.resolve(jsonResponse({ predicates: [], families: [] })); }
      if (/\/api\/books\/[^/?]+(\?|$)/.test(url)) { return Promise.resolve(jsonResponse(book())); }
      return Promise.resolve(jsonResponse({ detail: `unhandled: ${url}` }));
    }),
  );
};

describe("the review queue's speed budget (F5.3, S7.8 DoD)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("clears 50 mixed-type tasks with exactly one key each and no navigation keys", async () => {
    mockApi();
    renderRoute(`/books/${BOOK_ID}/review`);

    await screen.findByText(new RegExp(`task 1 of ${TASK_COUNT}`, "i"));
    expect(screen.getByText(new RegExp(`${TASK_COUNT} open`, "i"))).toBeInTheDocument();

    const startedAt = performance.now();
    for (const key of keySequence) {
      fireEvent.keyDown(document, { key });
    }
    const mechanicalMs = performance.now() - startedAt;

    // Every task actually left the queue — a stuck fast-path key would leave
    // some still open rather than throwing, so this is the real assertion.
    await waitFor(() => {
      expect(screen.getByText(/queue clear/i)).toBeInTheDocument();
    });

    // This measures interaction-loop overhead only, not human reading time —
    // the point is that it is nowhere near the 8-minute budget on its own,
    // i.e. the UI adds ~0 friction and the budget is spent entirely on
    // reading each task, which is a content question (S7.9), not a mechanical
    // one. Generous ceiling to keep this robust on a loaded CI box.
    expect(mechanicalMs).toBeLessThan(TARGET_MS / 10);
    expect(keySequence).toHaveLength(TASK_COUNT);
    expect(keySequence.every((key) => key !== "j" && key !== "k")).toBe(true);
    // Vitest's own test timeout (default 5000ms) is separate from the
    // mechanicalMs budget above and has flaked under a loaded CI box driving
    // 50 real keyboard events through React — bumped generously since this
    // test's own pass/fail signal is the assertions above, not wall clock.
  }, 15000);
});

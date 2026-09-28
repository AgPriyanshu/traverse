import { describe, expect, it } from "vitest";
import {
  buildPositionSteps,
  indexForPosition,
  limitsForBook,
  positionForIndex,
  positionLabel,
} from "@/lib/reading-position";
import type { Book } from "@/lib/api";

const book = (overrides: Record<string, unknown> = {}) =>
  ({
    id: "book-1",
    project_id: "project-1",
    series_order: 1,
    title: "Anne of Green Gables",
    author: "L. M. Montgomery",
    page_count: 300,
    chapter_count: 3,
    character_count: 3,
    status: "ready",
    ingested_at: null,
    ...overrides,
  }) as unknown as Book;

describe("buildPositionSteps", () => {
  it("lays every book's chapters end to end, in series order", () => {
    const books = [
      book({ id: "b2", series_order: 2, title: "Anne of Avonlea", chapter_count: 2 }),
      book({ id: "b1", series_order: 1, title: "Anne of Green Gables", chapter_count: 3 }),
    ];
    const steps = buildPositionSteps(books);
    expect(steps).toHaveLength(5);
    expect(steps.map((step) => `${step.bookOrder}.${step.chapter}`)).toEqual([
      "1.1", "1.2", "1.3", "2.1", "2.2",
    ]);
    expect(steps[3]?.bookTitle).toBe("Anne of Avonlea");
  });

  it("still contributes one step for a book with no chapters detected yet", () => {
    const steps = buildPositionSteps([book({ chapter_count: 0 })]);
    expect(steps).toHaveLength(1);
  });
});

describe("indexForPosition / positionForIndex", () => {
  const steps = buildPositionSteps([
    book({ id: "b1", series_order: 1, chapter_count: 3 }),
    book({ id: "b2", series_order: 2, title: "Anne of Avonlea", chapter_count: 2 }),
  ]);

  it("maps null to one past the last step — caught up", () => {
    expect(indexForPosition(null, steps)).toBe(steps.length);
    expect(positionForIndex(steps.length, steps)).toBeNull();
  });

  it("round-trips a real position", () => {
    const position = { bookOrder: 2, chapter: 1 };
    const index = indexForPosition(position, steps);
    expect(index).toBe(3);
    expect(positionForIndex(index, steps)).toEqual(position);
  });

  it("clamps a stale position (chapter count shrank since it was saved) to that book's last known step", () => {
    const index = indexForPosition({ bookOrder: 1, chapter: 99 }, steps);
    expect(steps[index]).toMatchObject({ bookOrder: 1, chapter: 3 });
  });
});

describe("positionLabel", () => {
  const steps = buildPositionSteps([book({ chapter_count: 5 })]);

  it("names the book and chapter when limited", () => {
    expect(positionLabel({ bookOrder: 1, chapter: 2 }, steps)).toMatch(
      /chapter 2 of anne of green gables/i,
    );
  });

  it("says caught up with no limit", () => {
    expect(positionLabel(null, steps)).toMatch(/caught up/i);
  });
});

describe("limitsForBook", () => {
  it("leaves a book before the reader's position uncapped", () => {
    expect(limitsForBook({ bookOrder: 2, chapter: 1 }, 1)).toEqual({
      limitBookOrder: 1,
      limitChapter: null,
    });
  });

  it("hides a book the reader hasn't reached yet entirely", () => {
    expect(limitsForBook({ bookOrder: 1, chapter: 5 }, 2)).toEqual({
      limitBookOrder: 2,
      limitChapter: 0,
    });
  });

  it("caps the book the reader is currently in at its own chapter", () => {
    expect(limitsForBook({ bookOrder: 1, chapter: 5 }, 1)).toEqual({
      limitBookOrder: 1,
      limitChapter: 5,
    });
  });

  it("leaves every book uncapped when the reader is caught up", () => {
    expect(limitsForBook(null, 3)).toEqual({ limitBookOrder: 3, limitChapter: null });
  });
});

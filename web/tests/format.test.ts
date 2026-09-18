import { describe, expect, it } from "vitest";
import {
  formatAliasRun,
  formatBytes,
  formatChapterLabel,
  formatCount,
  formatDuration,
  formatPageRange,
  formatRelativeTime,
  formatSecondsRemaining,
  pageRefLabel,
} from "@/lib/format";

describe("formatPageRange", () => {
  it("renders a single page as a bare figure", () => {
    expect(formatPageRange(214)).toBe("214");
  });

  it("collapses a range whose ends match", () => {
    expect(formatPageRange(214, 214)).toBe("214");
  });

  it("joins a real range with an en dash, not a hyphen", () => {
    expect(formatPageRange(214, 216)).toBe("214–216");
  });

  it("treats a null end page as a single page", () => {
    expect(formatPageRange(7, null)).toBe("7");
  });
});

describe("pageRefLabel", () => {
  it("names the book and the page, never a bare number", () => {
    expect(pageRefLabel(214, null, "Pride and Prejudice")).toBe(
      "page 214 of Pride and Prejudice",
    );
  });

  it("speaks a range as words rather than a dash", () => {
    expect(pageRefLabel(214, 216, "Persuasion")).toBe(
      "pages 214 to 216 of Persuasion",
    );
  });

  it("still says 'page' when the book title is unknown", () => {
    expect(pageRefLabel(3, undefined, undefined)).toBe("page 3");
  });
});

describe("formatChapterLabel", () => {
  it("numbers a chapter", () => {
    expect(formatChapterLabel(12)).toBe("Chapter 12");
  });

  it("appends a title with a middot", () => {
    expect(formatChapterLabel(12, "The Ball")).toBe("Chapter 12 · The Ball");
  });

  it("falls back for text outside any chapter", () => {
    expect(formatChapterLabel(null)).toBe("Unchaptered");
    expect(formatChapterLabel(null, "Preface")).toBe("Preface");
  });
});

describe("formatDuration", () => {
  it("renders sub-second work in milliseconds", () => {
    expect(formatDuration(420)).toBe("420 ms");
  });

  it("keeps one decimal below ten seconds", () => {
    expect(formatDuration(1234)).toBe("1.2 s");
  });

  it("drops the decimal above ten seconds", () => {
    expect(formatDuration(42_000)).toBe("42 s");
  });

  it("splits minutes and seconds", () => {
    expect(formatDuration(200_000)).toBe("3 m 20 s");
    expect(formatDuration(180_000)).toBe("3 m");
  });

  it("splits hours and minutes for a long ingestion", () => {
    expect(formatDuration(3_900_000)).toBe("1 h 5 m");
  });

  it("renders an em dash for an unknown duration", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
  });
});

describe("formatSecondsRemaining", () => {
  it("phrases an estimate", () => {
    expect(formatSecondsRemaining(200)).toBe("about 3 m 20 s remaining");
  });

  it("says nothing when there is nothing to say", () => {
    expect(formatSecondsRemaining(0)).toBeNull();
    expect(formatSecondsRemaining(null)).toBeNull();
  });
});

describe("formatRelativeTime", () => {
  const now = new Date("2026-09-17T12:00:00Z");

  it("reads in hours", () => {
    expect(formatRelativeTime("2026-09-17T09:00:00Z", now)).toBe("3 hours ago");
  });

  it("reads in days", () => {
    expect(formatRelativeTime("2026-09-14T12:00:00Z", now)).toBe("3 days ago");
  });

  it("handles a missing or unparseable timestamp", () => {
    expect(formatRelativeTime(null, now)).toBe("—");
    expect(formatRelativeTime("not a date", now)).toBe("—");
  });
});

describe("formatCount", () => {
  it("agrees in number", () => {
    expect(formatCount(1, "chapter")).toBe("1 chapter");
    expect(formatCount(12, "chapter")).toBe("12 chapters");
  });

  it("takes an irregular plural", () => {
    expect(formatCount(2, "person", "people")).toBe("2 people");
  });

  it("marks an unknown count rather than printing zero", () => {
    expect(formatCount(null, "page")).toBe("— pages");
  });
});

describe("formatBytes", () => {
  it("scales through the units", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
    expect(formatBytes(210 * 1024 * 1024)).toBe("210 MB");
  });
});

describe("formatAliasRun", () => {
  it("separates variant forms with middots, the way a concordance does", () => {
    expect(formatAliasRun(["Elizabeth", "Lizzy", "Miss Bennet"])).toBe(
      "Elizabeth · Lizzy · Miss Bennet",
    );
  });
});

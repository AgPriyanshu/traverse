import type { Chapter } from "@/lib/api";

/**
 * `MentionOut` carries a page, not a chapter — the same join
 * `mentions_per_chapter` must already do server-side, done here client-side
 * so clicking a timeline bar can filter the mention list by chapter. Returns
 * `undefined` when no chapter's range contains the page — expected, not a
 * bug, on the carried chapter-detection gap (plans/sprint-2/RETRO.md §4):
 * a book with zero detected chapters can't bucket anything, and the
 * timeline/list just fall back to showing everything unfiltered.
 */
export const chapterForPage = (
  chapters: readonly Chapter[],
  page: number,
): Chapter | undefined => {
  return chapters.find(
    (chapter) => page >= chapter.page_start && page <= chapter.page_end,
  );
};

/** `mentions_per_chapter`'s keys are chapter numbers stringified — match that shape exactly, including the fallback for an unchaptered mention. */
export const chapterKeyForPage = (
  chapters: readonly Chapter[],
  page: number,
): string => {
  const chapter = chapterForPage(chapters, page);
  return chapter?.number !== null && chapter?.number !== undefined
    ? String(chapter.number)
    : "null";
};

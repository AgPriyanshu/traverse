const EN_DASH = "–";

/**
 * The visible form of a citation: a bare figure, or a range with an en dash,
 * set the way a printed index sets one. The accessible name is built by
 * `pageRefLabel` instead — a screen reader must never hear just "214".
 */
export const formatPageRange = (
  pageStart: number,
  pageEnd?: number | null,
): string => {
  if (pageEnd === undefined || pageEnd === null || pageEnd === pageStart) {
    return String(pageStart);
  }
  return `${pageStart}${EN_DASH}${pageEnd}`;
};

export const pageRefLabel = (
  pageStart: number,
  pageEnd: number | null | undefined,
  bookTitle: string | null | undefined,
): string => {
  const isRange =
    pageEnd !== undefined && pageEnd !== null && pageEnd !== pageStart;
  const pages = isRange
    ? `pages ${pageStart} to ${pageEnd}`
    : `page ${pageStart}`;
  return bookTitle ? `${pages} of ${bookTitle}` : pages;
};

export const formatChapterLabel = (
  chapterNo: number | null | undefined,
  title?: string | null,
): string => {
  if (chapterNo === null || chapterNo === undefined) {
    return title ?? "Unchaptered";
  }
  return title ? `Chapter ${chapterNo} · ${title}` : `Chapter ${chapterNo}`;
};

const SECOND = 1000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;

/** Ingestion durations, read at a glance rather than compared to the millisecond. */
export const formatDuration = (milliseconds: number | null | undefined): string => {
  if (milliseconds === null || milliseconds === undefined) { return "—"; }
  if (milliseconds < SECOND) { return `${Math.round(milliseconds)} ms`; }

  if (milliseconds < MINUTE) {
    const seconds = milliseconds / SECOND;
    return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)} s`;
  }

  if (milliseconds < HOUR) {
    const minutes = Math.floor(milliseconds / MINUTE);
    const seconds = Math.round((milliseconds % MINUTE) / SECOND);
    return seconds > 0 ? `${minutes} m ${seconds} s` : `${minutes} m`;
  }

  const hours = Math.floor(milliseconds / HOUR);
  const minutes = Math.round((milliseconds % HOUR) / MINUTE);
  return minutes > 0 ? `${hours} h ${minutes} m` : `${hours} h`;
};

export const formatSecondsRemaining = (
  seconds: number | null | undefined,
): string | null => {
  if (seconds === null || seconds === undefined || seconds <= 0) { return null; }
  return `about ${formatDuration(seconds * SECOND)} remaining`;
};

const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * HOUR],
  ["month", 30 * 24 * HOUR],
  ["week", 7 * 24 * HOUR],
  ["day", 24 * HOUR],
  ["hour", HOUR],
  ["minute", MINUTE],
];

export const formatRelativeTime = (
  iso: string | null | undefined,
  now: Date = new Date(),
): string => {
  if (!iso) { return "—"; }

  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) { return "—"; }

  const elapsed = then.getTime() - now.getTime();
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

  for (const [unit, span] of RELATIVE_UNITS) {
    if (Math.abs(elapsed) >= span) {
      return formatter.format(Math.round(elapsed / span), unit);
    }
  }

  return formatter.format(Math.round(elapsed / SECOND), "second");
};

export const formatAbsoluteTime = (iso: string | null | undefined): string => {
  if (!iso) { return "—"; }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) { return "—"; }
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
};

export const formatCount = (
  value: number | null | undefined,
  singular: string,
  plural = `${singular}s`,
): string => {
  if (value === null || value === undefined) { return `— ${plural}`; }
  return `${value.toLocaleString()} ${value === 1 ? singular : plural}`;
};

const KILOBYTE = 1024;

export const formatBytes = (bytes: number): string => {
  if (bytes < KILOBYTE) { return `${bytes} B`; }
  const units = ["KB", "MB", "GB"];
  let value = bytes / KILOBYTE;
  let unitIndex = 0;
  while (value >= KILOBYTE && unitIndex < units.length - 1) {
    value /= KILOBYTE;
    unitIndex += 1;
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unitIndex]}`;
};

/** "Elizabeth · Lizzy · Miss Bennet" — a concordance's run of variant forms. */
export const formatAliasRun = (aliases: readonly string[]): string => {
  return aliases.join(" · ");
};

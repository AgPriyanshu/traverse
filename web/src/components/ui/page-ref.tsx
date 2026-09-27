import { Link, Span } from "@chakra-ui/react";
import { Link as RouterLink } from "react-router";
import { formatPageRange, pageRefLabel } from "@/lib/format";
import type { SpanBox } from "@/lib/api";

export type PageRefProps = {
  page: number;
  pageEnd?: number | null;
  bookId?: string | null;
  bookTitle?: string | null;
  /** The page image has not been rendered yet, so there is nowhere to go. */
  unavailable?: boolean;
  /**
   * When present, the link carries `?highlight=x,y,w,h` (`routes/book/page.tsx`'s
   * `parseHighlight`) so the page viewer draws the exact quoted span rather
   * than just opening the page. Most citations don't have one yet —
   * `CitationOut` has no `span` field (Sprint 6 SCR) — so this degrades to a
   * plain page link, exactly like `MentionOut`'s citations do (Sprint 3 SCR-2).
   */
  span?: SpanBox | null;
  /**
   * Renders a superscript footnote mark ("¹") instead of "p. 214" — for a
   * citation inline in the middle of a sentence, where the full typographic
   * reference would break the reading flow (S6.10). Still a `PageRef`
   * underneath: same link semantics, same accessible name.
   */
  index?: number;
};

const SUPERSCRIPT_DIGITS: Record<string, string> = {
  "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
  "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
};

const toSuperscript = (value: number): string =>
  String(value)
    .split("")
    .map((digit) => SUPERSCRIPT_DIGITS[digit] ?? digit)
    .join("");

const HAIR_SPACE = " ";

/**
 * A citation, set the way a printed book sets a cross-reference: oldstyle
 * tabular figures under a hairline dotted rule. No capsule, no fill, no pill —
 * a tinted chip was tried and rejected as generic product UI in a tool whose
 * whole subject is books (design/DESIGN.md §2).
 *
 * It is a link, and its accessible name always carries the book and the page.
 */
export const PageRef = ({
  page,
  pageEnd,
  bookId,
  bookTitle,
  unavailable = false,
  span,
  index,
}: PageRefProps) => {
  // Variables.
  const figures = formatPageRange(page, pageEnd);
  const baseLabel = pageRefLabel(page, pageEnd, bookTitle);
  const label = index === undefined ? baseLabel : `citation ${index}: ${baseLabel}`;
  const isLinkable = Boolean(bookId) && !unavailable;
  const href =
    span !== undefined && span !== null
      ? `/books/${bookId}/pages/${page}?highlight=${span.x},${span.y},${span.width},${span.height}`
      : `/books/${bookId}/pages/${page}`;

  const marks =
    index === undefined ? (
      <>
        <Span aria-hidden="true" color="fg.subtle">
          p.
        </Span>
        {HAIR_SPACE}
        {figures}
      </>
    ) : (
      // Unicode superscript figures, not a CSS transform — a footnote mark
      // set the way a printed book sets one, no arbitrary font-size scaling.
      <Span aria-hidden="true">{toSuperscript(index)}</Span>
    );

  const shared = {
    textStyle: "data",
    whiteSpace: "nowrap" as const,
    borderBottomWidth: index === undefined ? "1px" : "0",
    borderBottomStyle: "dotted" as const,
  };

  // Early returns.
  if (!isLinkable) {
    return (
      <Span
        {...shared}
        color="fg.subtle"
        borderBottomColor="border"
        aria-label={`${label} — not available yet`}
        title="This page has not been rendered yet."
      >
        {marks}
      </Span>
    );
  }

  return (
    <Link
      asChild
      {...shared}
      color="fg.subtle"
      borderBottomColor="border.control"
      textDecoration="none"
      transitionProperty="color, border-color"
      transitionDuration="fast"
      _hover={{ color: "accent.fg", borderBottomColor: "accent.solid" }}
    >
      <RouterLink to={href} aria-label={label}>
        {marks}
      </RouterLink>
    </Link>
  );
};

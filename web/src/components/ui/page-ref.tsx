import { Link, Span } from "@chakra-ui/react";
import { Link as RouterLink } from "react-router";
import { formatPageRange, pageRefLabel } from "@/lib/format";

export type PageRefProps = {
  page: number;
  pageEnd?: number | null;
  bookId?: string | null;
  bookTitle?: string | null;
  /** The page image has not been rendered yet, so there is nowhere to go. */
  unavailable?: boolean;
};

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
}: PageRefProps) => {
  // Variables.
  const figures = formatPageRange(page, pageEnd);
  const label = pageRefLabel(page, pageEnd, bookTitle);
  const isLinkable = Boolean(bookId) && !unavailable;

  const marks = (
    <>
      <Span aria-hidden="true" color="fg.subtle">
        p.
      </Span>
      {HAIR_SPACE}
      {figures}
    </>
  );

  const shared = {
    textStyle: "data",
    whiteSpace: "nowrap" as const,
    borderBottomWidth: "1px",
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
      <RouterLink to={`/books/${bookId}/pages/${page}`} aria-label={label}>
        {marks}
      </RouterLink>
    </Link>
  );
};

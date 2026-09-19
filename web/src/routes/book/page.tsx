import { Heading, Stack } from "@chakra-ui/react";
import { useCallback, useMemo } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { ErrorState } from "@/components/ui";
import { useBook } from "@/lib/api";
import type { Highlight } from "./page-viewer";
import { PageViewer } from "./page-viewer";

/**
 * `?highlight=x,y,w,h` — four PDF-user-space numbers (the `SpanBox`
 * coordinate space, HANDOFF.md), comma-separated. This is what Sprint 6's
 * citation links write; a malformed or absent value just means no highlight,
 * not a broken page.
 */
const parseHighlight = (raw: string | null, page: number): Highlight[] => {
  if (!raw) { return []; }
  const [x, y, w, h] = raw.split(",").map((part) => Number.parseFloat(part));
  if ([x, y, w, h].some((value) => value === undefined || Number.isNaN(value))) {
    return [];
  }
  return [{ page, x: x as number, y: y as number, w: w as number, h: h as number, kind: "citation" }];
};

export const BookPage = () => {
  // Hooks.
  const { bookId = "", page: pageParam = "" } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  // Apis.
  const book = useBook(bookId);

  // Variables.
  const page = Number.parseInt(pageParam, 10);
  const isValidPage = Number.isInteger(page) && page >= 1;

  // useMemos.
  const highlights = useMemo(
    () => (isValidPage ? parseHighlight(searchParams.get("highlight"), page) : []),
    [searchParams, page, isValidPage],
  );

  // Handlers.
  const handleNavigate = useCallback(
    (nextPage: number) => { navigate(`/books/${bookId}/pages/${nextPage}`); },
    [bookId, navigate],
  );

  // Early returns.
  if (!isValidPage) {
    return (
      <ErrorState
        error={new Error(`"${pageParam}" is not a valid page number.`)}
        title="Invalid page"
      />
    );
  }

  return (
    <Stack gap="5">
      <Heading as="h2" textStyle="heading">
        Page {page}
      </Heading>
      <PageViewer
        bookId={bookId}
        page={page}
        pageCount={book.data?.page_count}
        highlights={highlights}
        onNavigate={handleNavigate}
      />
    </Stack>
  );
};

export default BookPage;

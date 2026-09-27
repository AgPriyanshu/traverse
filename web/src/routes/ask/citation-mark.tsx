import { Span } from "@chakra-ui/react";
import { PageRef } from "@/components/ui";
import type { Citation } from "@/lib/api";

export type CitationMarkProps = {
  index: number;
  citation: Citation;
};

/**
 * The inline citation for a claim mid-sentence — a superscript `PageRef`
 * (S6.10), never a pill (design/DESIGN.md §2). The native `title` is a cheap
 * hover preview of the quote it is citing; `<PageRef>` itself carries the
 * real accessible name and the click-through.
 */
export const CitationMark = ({ index, citation }: CitationMarkProps) => {
  return (
    <Span title={citation.quote ?? undefined}>
      <PageRef
        index={index}
        page={citation.page_start}
        pageEnd={citation.page_end}
        bookId={citation.book_id}
        bookTitle={citation.book_title}
      />
    </Span>
  );
};

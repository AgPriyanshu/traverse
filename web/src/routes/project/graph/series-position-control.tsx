import { Box, HStack, Text, chakra } from "@chakra-ui/react";
import type { Book } from "@/lib/api";
import { sortedBooks } from "../project-lookup";

const Select = chakra("select");

export type SeriesPosition = {
  bookOrder: number | null;
  chapter: number | null;
};

export type SeriesPositionControlProps = {
  books: readonly Book[];
  value: SeriesPosition;
  onChange: (next: SeriesPosition) => void;
};

/**
 * The spoiler gate: "reading position = book N, chapter M" must mean nothing
 * later renders (S5.11, PRD F3.6). This is a hard server-side cut
 * (`limit_book_order`/`limit_chapter` on `GET /projects/{id}/graph`), not a
 * client-side visual filter like the book slice above it — picking a
 * position re-fetches a smaller graph rather than animating one.
 *
 * Choosing a book always pins a real chapter too (defaulting to that book's
 * last one), so the pair sent to the API is never a book with an undefined
 * chapter — an ambiguity the contract's own `SeriesPosition` comparison
 * would otherwise have to guess at.
 */
export const SeriesPositionControl = ({ books, value, onChange }: SeriesPositionControlProps) => {
  // Variables.
  const ordered = sortedBooks(books);
  const currentBook = ordered.find((book) => book.series_order === value.bookOrder);
  const chapterCount = currentBook?.chapter_count ?? 0;

  return (
    <HStack
      as="fieldset"
      gap="4"
      wrap="wrap"
      align="center"
      borderWidth="1px"
      borderColor="border"
      borderRadius="md"
      bg="bg.sunken"
      paddingInline="3"
      paddingBlock="2"
    >
      <Text as="legend" textStyle="small" color="fg.muted" fontWeight="600">
        Reading position
      </Text>

      <Box as="label" display="flex" alignItems="center" gap="2">
        <Text as="span" textStyle="small" color="fg.muted">
          up to book
        </Text>
        <Select
          value={value.bookOrder === null ? "" : String(value.bookOrder)}
          onChange={(event) => {
            if (event.target.value === "") {
              onChange({ bookOrder: null, chapter: null });
              return;
            }
            const order = Number(event.target.value);
            const book = ordered.find((entry) => entry.series_order === order);
            onChange({ bookOrder: order, chapter: book?.chapter_count ?? 1 });
          }}
          textStyle="data"
          bg="bg.surface"
          color="fg"
          borderWidth="1px"
          borderColor="border.control"
          borderRadius="md"
          paddingInline="2"
          paddingBlock="1"
        >
          <option value="">caught up (no limit)</option>
          {ordered.map((book) => (
            <option key={book.id} value={book.series_order ?? ""}>
              {book.series_order}. {book.title}
            </option>
          ))}
        </Select>
      </Box>

      {value.bookOrder !== null ? (
        <Box as="label" display="flex" alignItems="center" gap="2">
          <Text as="span" textStyle="small" color="fg.muted">
            chapter
          </Text>
          <Select
            value={value.chapter === null ? "" : String(value.chapter)}
            onChange={(event) => {
              onChange({ bookOrder: value.bookOrder, chapter: Number(event.target.value) });
            }}
            textStyle="data"
            bg="bg.surface"
            color="fg"
            borderWidth="1px"
            borderColor="border.control"
            borderRadius="md"
            paddingInline="2"
            paddingBlock="1"
          >
            {Array.from({ length: Math.max(chapterCount, value.chapter ?? 1) }, (_unused, index) => index + 1).map(
              (number) => (
                <option key={number} value={number}>
                  {number}
                </option>
              ),
            )}
          </Select>
        </Box>
      ) : null}

      <Text textStyle="small" color="fg.subtle">
        Nothing past this point in the story renders, anywhere on this screen.
      </Text>
    </HStack>
  );
};

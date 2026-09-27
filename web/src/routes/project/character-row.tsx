import { Box, Link, Span, Text } from "@chakra-ui/react";
import { Link as RouterLink } from "react-router";
import { PageRef } from "@/components/ui";
import type { Book, Character } from "@/lib/api";
import { formatAliasRun, formatCount } from "@/lib/format";
import { AppearanceStrip } from "./appearance-strip";
import type { AppearanceSlot } from "./appearance-strip";
import { bookById } from "./project-lookup";

export type CharacterRowProps = {
  character: Character;
  projectId: string;
  books: readonly Book[];
};

const TOP_ALIAS_COUNT = 3;

/**
 * One series-roster entry: one row per character, never one per book — a
 * returning character is the same row gaining a filled slot, not a second
 * row (S5.10).
 */
export const CharacterRow = ({ character, projectId, books }: CharacterRowProps) => {
  // Variables.
  const aliases = character.aliases ?? [];
  const topAliases = aliases.slice(0, TOP_ALIAS_COUNT);
  const remainingAliasCount = aliases.length - topAliases.length;
  const byId = bookById(books);
  const firstBook = character.first_book_id ? byId.get(character.first_book_id) : undefined;
  const slots: AppearanceSlot[] = (character.appears_in_books ?? []).map((seriesOrder) => ({
    seriesOrder,
    isFirst: firstBook?.series_order === seriesOrder,
  }));
  const firstPageBookId = firstBook?.id ?? character.first_book_id ?? undefined;

  return (
    <Box
      as="li"
      display="flex"
      flexDirection={{ base: "column", md: "row" }}
      alignItems={{ base: "stretch", md: "center" }}
      gap={{ base: "2", md: "5" }}
      paddingInline={{ base: "4", md: "4.5" }}
      paddingBlock={{ base: "3.5", md: "3" }}
      borderTopWidth="1px"
      borderColor="border"
    >
      <Box flex={{ md: "0 0 14rem" }} minWidth="0">
        <Link asChild fontWeight="600">
          <RouterLink
            to={`/projects/${projectId}/characters/${character.id}`}
            style={{ display: "block" }}
          >
            <Text textStyle="subheading" as="span" color="fg" truncate>
              {character.canonical_name}
            </Text>
          </RouterLink>
        </Link>
        {slots.length === 1 && firstBook ? (
          <Text
            as="span"
            textStyle="small"
            color="accent.fg"
            fontWeight="600"
          >
            new in bk. {firstBook.series_order}
          </Text>
        ) : null}
        {aliases.length > 0 ? (
          <Text textStyle="quote" fontStyle="italic" color="fg.muted" truncate>
            {formatAliasRun(topAliases)}
            {remainingAliasCount > 0 ? (
              <Span textStyle="small" fontStyle="normal" color="fg.subtle">
                {" · "}and {remainingAliasCount} more
              </Span>
            ) : null}
          </Text>
        ) : null}
      </Box>

      <Box flex="1" minWidth="0">
        <AppearanceStrip
          totalSlots={Math.max(books.length, 1)}
          slots={slots}
          characterName={character.canonical_name}
        />
      </Box>

      <Box flex={{ md: "0 0 6rem" }} display="flex" justifyContent={{ md: "flex-end" }}>
        {character.first_page !== null && character.first_page !== undefined ? (
          <PageRef
            page={character.first_page}
            bookId={firstPageBookId}
            bookTitle={firstBook?.title}
          />
        ) : (
          <Text textStyle="data" color="fg.subtle">
            —
          </Text>
        )}
      </Box>

      <Text
        textStyle="data"
        color="fg.muted"
        flex={{ md: "0 0 6rem" }}
        textAlign={{ md: "right" }}
      >
        {formatCount(character.mention_count, "mention")}
      </Text>
    </Box>
  );
};

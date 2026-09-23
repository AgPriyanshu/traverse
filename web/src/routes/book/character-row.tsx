import { Box, HStack, Link, Span, Stack, Text } from "@chakra-ui/react";
import { Link as RouterLink } from "react-router";
import { PageRef } from "@/components/ui";
import type { Character } from "@/lib/api";
import { formatAliasRun, formatCount } from "@/lib/format";
import { SparklineBars } from "./sparkline-bars";

export type CharacterRowProps = {
  character: Character;
  bookId: string;
  bookTitle?: string | null;
};

const TOP_ALIAS_COUNT = 3;

/**
 * One roster entry. Aliases render as an italic serif run separated by
 * middots, the way a concordance sets variant forms — not a row of chips
 * (design/DESIGN.md §2 overrides the sprint brief's "alias chips" wording).
 */
export const CharacterRow = ({ character, bookId, bookTitle }: CharacterRowProps) => {
  // Variables.
  const aliases = character.aliases ?? [];
  const topAliases = aliases.slice(0, TOP_ALIAS_COUNT);
  const remainingAliasCount = aliases.length - topAliases.length;

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
      <Box flex={{ md: "0 0 15rem" }} minWidth="0">
        <Link asChild fontWeight="600">
          <RouterLink
            to={`/books/${bookId}/characters/${character.id}`}
            style={{ display: "block" }}
          >
            <Text textStyle="subheading" as="span" color="fg" truncate>
              {character.canonical_name}
            </Text>
          </RouterLink>
        </Link>
      </Box>

      <Box flex="1" minWidth="0">
        {aliases.length > 0 ? (
          <Text textStyle="quote" fontStyle="italic" color="fg.muted" truncate>
            {formatAliasRun(topAliases)}
            {remainingAliasCount > 0 ? (
              <Span
                textStyle="small"
                fontStyle="normal"
                color="fg.subtle"
              >
                {" · "}and {remainingAliasCount} more
              </Span>
            ) : null}
          </Text>
        ) : (
          <Text textStyle="small" color="fg.subtle">
            No other names recorded
          </Text>
        )}
      </Box>

      <HStack
        gap={{ base: "4", md: "5" }}
        justify={{ base: "space-between", md: "flex-end" }}
        flex={{ md: "0 0 auto" }}
      >
        <Text textStyle="data" color="fg.muted" flex={{ md: "0 0 5rem" }} textAlign={{ md: "right" }}>
          {formatCount(character.mention_count, "mention")}
        </Text>

        <Box flex={{ md: "0 0 6rem" }} display="flex" justifyContent={{ md: "flex-end" }}>
          {character.first_page !== null && character.first_page !== undefined ? (
            <PageRef page={character.first_page} bookId={bookId} bookTitle={bookTitle} />
          ) : (
            <Text textStyle="data" color="fg.subtle">
              —
            </Text>
          )}
        </Box>

        <Stack gap="0.5" flex={{ md: "0 0 9.5rem" }} display={{ base: "none", sm: "flex" }}>
          {/* `CharacterOut` (the list contract) has no per-chapter histogram yet —
             SCR-1, plans/sprint-3/SCR.md. `SparklineBars` degrades to a labelled
             placeholder rather than fabricating a chapter shape it doesn't have. */}
          <SparklineBars
            data={[]}
            width={148}
            height={26}
            ariaLabel={`mentions per chapter for ${character.canonical_name}`}
          />
        </Stack>
      </HStack>
    </Box>
  );
};

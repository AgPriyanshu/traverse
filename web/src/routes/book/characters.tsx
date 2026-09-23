import { Box, Button, Heading, HStack, Input, Stack, Text } from "@chakra-ui/react";
import { useMemo } from "react";
import { useParams, useSearchParams } from "react-router";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui";
import type { Character, ImportanceTier } from "@/lib/api";
import { useBook, useCharacters } from "@/lib/api";
import { formatCount } from "@/lib/format";
import { CharacterRow } from "./character-row";
import { TIER_LABEL, TIER_ORDER } from "./character-labels";

type SortKey = "mentions" | "first" | "name";

// A stable empty-array reference — `characters.data ?? []` would otherwise
// create a new array every render while pending, defeating the `useMemo`s
// below.
const EMPTY_ROSTER: Character[] = [];

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: "mentions", label: "Most mentioned" },
  { key: "first", label: "First appearance" },
  { key: "name", label: "Name" },
];

const matchesQuery = (character: Character, query: string): boolean => {
  const needle = query.trim().toLowerCase();
  if (needle === "") { return true; }
  if (character.canonical_name.toLowerCase().includes(needle)) { return true; }
  return (character.aliases ?? []).some((alias) => alias.toLowerCase().includes(needle));
};

const sortCharacters = (characters: Character[], sort: SortKey): Character[] => {
  const sorted = [...characters];
  if (sort === "name") {
    sorted.sort((a, b) => a.canonical_name.localeCompare(b.canonical_name));
    return sorted;
  }
  if (sort === "first") {
    sorted.sort((a, b) => (a.first_page ?? Infinity) - (b.first_page ?? Infinity));
    return sorted;
  }
  sorted.sort((a, b) => b.mention_count - a.mention_count);
  return sorted;
};

export const Characters = () => {
  // Hooks.
  const { bookId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();

  // Apis.
  const book = useBook(bookId);
  const projectId = book.data?.project_id;
  const characters = useCharacters(projectId, { book_id: bookId });

  // Variables.
  const query = searchParams.get("q") ?? "";
  const tierFilter = (searchParams.get("tier") as ImportanceTier | null) ?? null;
  const sort = (searchParams.get("sort") as SortKey | null) ?? "mentions";

  // useMemos.
  const roster = characters.data ?? EMPTY_ROSTER;
  const totalMentions = useMemo(
    () => roster.reduce((sum, character) => sum + character.mention_count, 0),
    [roster],
  );
  const tierCounts = useMemo(() => {
    const counts = new Map<ImportanceTier, number>();
    for (const character of roster) {
      counts.set(character.importance_tier, (counts.get(character.importance_tier) ?? 0) + 1);
    }
    return counts;
  }, [roster]);
  const visible = useMemo(() => {
    const filtered = roster.filter(
      (character) =>
        matchesQuery(character, query) &&
        (tierFilter === null || character.importance_tier === tierFilter),
    );
    return sortCharacters(filtered, sort);
  }, [roster, query, tierFilter, sort]);
  const grouped = useMemo(() => {
    const groups = new Map<ImportanceTier, Character[]>();
    for (const character of visible) {
      const bucket = groups.get(character.importance_tier) ?? [];
      bucket.push(character);
      groups.set(character.importance_tier, bucket);
    }
    return TIER_ORDER.map((tier) => ({ tier, characters: groups.get(tier) ?? [] })).filter(
      (group) => group.characters.length > 0,
    );
  }, [visible]);

  // Handlers.
  const updateParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (value === null || value === "") {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    setSearchParams(next, { replace: true });
  };

  // Early returns.
  // `useCharacters` depends on `book.data.project_id`, so a failed book fetch
  // (e.g. the route's own contract not built yet) would otherwise leave the
  // characters query permanently disabled — spinning forever rather than
  // surfacing the real error.
  if (book.error) {
    return <ErrorState error={book.error} onRetry={() => void book.refetch()} />;
  }

  return (
    <Stack gap="7">
      <Stack gap="2">
        <Heading as="h2" textStyle="heading">
          Everyone in this book
        </Heading>
        {roster.length > 0 ? (
          <Text textStyle="body" color="fg.muted" maxW="measure">
            {formatCount(roster.length, "person", "people")}, gathered from{" "}
            {formatCount(totalMentions, "mention")}
            {book.data?.chapter_count
              ? ` across ${formatCount(book.data.chapter_count, "chapter")}`
              : ""}
            . Names that turned out to be the same person have been folded
            together — open anyone to see why.
          </Text>
        ) : null}
      </Stack>

      <Stack gap="4">
        <HStack gap="3" wrap="wrap">
          <Input
            value={query}
            onChange={(event) => { updateParam("q", event.target.value); }}
            placeholder='Try "Lizzy"'
            aria-label="Search characters by name or alias"
            borderColor="border.control"
            borderRadius="md"
            bg="bg.surface"
            textStyle="body"
            maxW="16rem"
          />

          <HStack gap="1.5" wrap="wrap" role="group" aria-label="Filter by tier">
            <TierFilterButton
              label="All"
              active={tierFilter === null}
              onClick={() => { updateParam("tier", null); }}
            />
            {TIER_ORDER.filter((tier) => (tierCounts.get(tier) ?? 0) > 0).map((tier) => (
              <TierFilterButton
                key={tier}
                label={`${TIER_LABEL[tier]} (${tierCounts.get(tier) ?? 0})`}
                active={tierFilter === tier}
                onClick={() => { updateParam("tier", tierFilter === tier ? null : tier); }}
              />
            ))}
          </HStack>

          <HStack gap="1.5" wrap="wrap" role="group" aria-label="Sort by">
            {SORT_OPTIONS.map((option) => (
              <TierFilterButton
                key={option.key}
                label={option.label}
                active={sort === option.key}
                onClick={() => { updateParam("sort", option.key); }}
              />
            ))}
          </HStack>
        </HStack>
      </Stack>

      {characters.isPending ? (
        <LoadingSkeleton variant="cards" count={6} label="Loading the roster" />
      ) : null}

      {characters.error ? (
        <ErrorState error={characters.error} onRetry={() => void characters.refetch()} />
      ) : null}

      {!characters.isPending && !characters.error && roster.length === 0 ? (
        <EmptyState
          title="No characters yet"
          description="Character extraction runs after ingestion finishes — check the overview tab for where this book's run stands."
        />
      ) : null}

      {!characters.isPending && !characters.error && roster.length > 0 && visible.length === 0 ? (
        <EmptyState
          title="No one matches"
          description="Try a different name, alias, or tier filter."
        />
      ) : null}

      {grouped.map((group) => (
        <Stack as="section" gap="3" key={group.tier}>
          <HStack gap="2.5" align="baseline">
            <Heading as="h3" textStyle="subheading">
              {TIER_LABEL[group.tier]}
            </Heading>
            <Text textStyle="data" color="fg.subtle">
              {group.characters.length}
            </Text>
          </HStack>

          <Box
            as="ul"
            listStyleType="none"
            paddingInline="0"
            borderWidth="1px"
            borderColor="border"
            borderRadius="lg"
            bg="bg.surface"
            overflow="hidden"
          >
            {group.characters.map((character) => (
              <CharacterRow
                key={character.id}
                character={character}
                bookId={bookId}
                bookTitle={book.data?.title}
              />
            ))}
          </Box>
        </Stack>
      ))}
    </Stack>
  );
};

const TierFilterButton = ({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) => {
  return (
    <Button
      size="sm"
      variant="outline"
      textStyle="small"
      fontWeight={active ? "600" : "400"}
      borderRadius="md"
      borderColor={active ? "accent.solid" : "border.control"}
      bg={active ? "accent.subtle" : "bg.surface"}
      color={active ? "accent.fg" : "fg.muted"}
      aria-pressed={active}
      onClick={onClick}
    >
      {label}
    </Button>
  );
};

export default Characters;

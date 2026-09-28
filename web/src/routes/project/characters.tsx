import { Box, Button, Heading, HStack, Input, Stack, Text } from "@chakra-ui/react";
import { useMemo } from "react";
import { useParams, useSearchParams } from "react-router";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui";
import type { Book, Character, ImportanceTier } from "@/lib/api";
import { useCharacters, useProject } from "@/lib/api";
import { formatCount } from "@/lib/format";
import { CharacterRow } from "./character-row";
import { TIER_LABEL, TIER_ORDER } from "./character-labels";
import { bookById, sortedBooks } from "./project-lookup";
import { useReadingPositionContext } from "./reading-position-context";

type SortKey = "mentions" | "first" | "name";

const EMPTY_ROSTER: Character[] = [];
const EMPTY_BOOKS: Book[] = [];

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
    sorted.sort(
      (a, b) =>
        (a.first_book_id === b.first_book_id ? 0 : 1) ||
        (a.first_page ?? Infinity) - (b.first_page ?? Infinity),
    );
    return sorted;
  }
  sorted.sort((a, b) => b.mention_count - a.mention_count);
  return sorted;
};

/**
 * The series roster: one row per character, not one per book (S5.10). A
 * returning character's appearance strip is the answer to "which books is
 * this person in" — the reason this screen exists rather than a per-book
 * copy of Sprint 3's roster.
 */
export const Characters = () => {
  // Hooks.
  const { projectId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();

  // Context.
  const { position } = useReadingPositionContext();

  // Apis.
  const project = useProject(projectId);
  const characters = useCharacters(projectId, {
    limit_book_order: position?.bookOrder ?? undefined,
    limit_chapter: position?.chapter ?? undefined,
  });

  // Variables.
  const query = searchParams.get("q") ?? "";
  const tierFilter = (searchParams.get("tier") as ImportanceTier | null) ?? null;
  const sort = (searchParams.get("sort") as SortKey | null) ?? "mentions";
  const newInBook = searchParams.get("new");
  const newInBookOrder = newInBook === null ? null : Number(newInBook);

  // useMemos.
  const books = useMemo(() => sortedBooks(project.data?.books ?? EMPTY_BOOKS), [project.data]);
  const byId = useMemo(() => bookById(books), [books]);
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
    const filtered = roster.filter((character) => {
      if (!matchesQuery(character, query)) { return false; }
      if (tierFilter !== null && character.importance_tier !== tierFilter) { return false; }
      if (newInBookOrder !== null) {
        const firstBook = character.first_book_id ? byId.get(character.first_book_id) : undefined;
        if (firstBook?.series_order !== newInBookOrder) { return false; }
      }
      return true;
    });
    return sortCharacters(filtered, sort);
  }, [roster, query, tierFilter, newInBookOrder, byId, sort]);
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
  if (project.error) {
    return <ErrorState error={project.error} onRetry={() => void project.refetch()} />;
  }

  return (
    <Stack gap="7">
      <Stack gap="2">
        <Heading as="h2" textStyle="heading">
          Everyone in {project.data?.name ?? "this series"}
        </Heading>
        {roster.length > 0 ? (
          <Text textStyle="body" color="fg.muted" maxW="measure">
            {formatCount(roster.length, "person", "people")}, gathered from{" "}
            {formatCount(totalMentions, "mention")}
            {books.length > 1 ? ` across ${formatCount(books.length, "book")}` : ""}.
            A returning character keeps one row — open anyone to see which
            volumes they appear in and where they first turn up in each.
          </Text>
        ) : null}
      </Stack>

      <Stack gap="4">
        <HStack gap="3" wrap="wrap">
          <Input
            value={query}
            onChange={(event) => { updateParam("q", event.target.value); }}
            placeholder='Try "Anne"'
            aria-label="Search characters by name or alias"
            borderColor="border.control"
            borderRadius="md"
            bg="bg.surface"
            textStyle="body"
            maxW="16rem"
          />

          <HStack gap="1.5" wrap="wrap" role="group" aria-label="Filter by tier">
            <FilterButton
              label="All"
              active={tierFilter === null}
              onClick={() => { updateParam("tier", null); }}
            />
            {TIER_ORDER.filter((tier) => (tierCounts.get(tier) ?? 0) > 0).map((tier) => (
              <FilterButton
                key={tier}
                label={`${TIER_LABEL[tier]} (${tierCounts.get(tier) ?? 0})`}
                active={tierFilter === tier}
                onClick={() => { updateParam("tier", tierFilter === tier ? null : tier); }}
              />
            ))}
          </HStack>

          {books.length > 1 ? (
            <HStack gap="1.5" wrap="wrap" role="group" aria-label="New in book">
              <FilterButton
                label="Any book"
                active={newInBookOrder === null}
                onClick={() => { updateParam("new", null); }}
              />
              {books.map((book) => (
                <FilterButton
                  key={book.id}
                  label={`New in bk. ${book.series_order ?? "?"}`}
                  active={newInBookOrder === book.series_order}
                  onClick={() => {
                    updateParam(
                      "new",
                      newInBookOrder === book.series_order ? null : String(book.series_order ?? ""),
                    );
                  }}
                />
              ))}
            </HStack>
          ) : null}

          <HStack gap="1.5" wrap="wrap" role="group" aria-label="Sort by">
            {SORT_OPTIONS.map((option) => (
              <FilterButton
                key={option.key}
                label={option.label}
                active={sort === option.key}
                onClick={() => { updateParam("sort", option.key); }}
              />
            ))}
          </HStack>
        </HStack>
      </Stack>

      {characters.isPending || project.isPending ? (
        <LoadingSkeleton variant="cards" count={6} label="Loading the roster" />
      ) : null}

      {characters.error ? (
        <ErrorState error={characters.error} onRetry={() => void characters.refetch()} />
      ) : null}

      {!characters.isPending && !characters.error && roster.length === 0 ? (
        <EmptyState
          title="No characters yet"
          description="Character extraction runs after ingestion finishes — check a book's overview tab for where its run stands."
        />
      ) : null}

      {!characters.isPending && !characters.error && roster.length > 0 && visible.length === 0 ? (
        <EmptyState
          title="No one matches"
          description="Try a different name, alias, tier, or 'new in book' filter."
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
                projectId={projectId}
                books={books}
              />
            ))}
          </Box>
        </Stack>
      ))}
    </Stack>
  );
};

const FilterButton = ({
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

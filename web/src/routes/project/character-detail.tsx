import { Box, Button, Flex, HStack, Heading, Link, Span, Stack, Text, chakra } from "@chakra-ui/react";
import { useMemo, useState } from "react";
import { Link as RouterLink, useParams, useSearchParams } from "react-router";
import { ErrorState, LoadingSkeleton, PageRef } from "@/components/ui";
import type { Book, Chapter } from "@/lib/api";
import { useCharacter, useChapters, useProject } from "@/lib/api";
import { formatCount } from "@/lib/format";
import { AppearanceStrip } from "./appearance-strip";
import type { AppearanceSlot } from "./appearance-strip";
import { chapterKeyForPage } from "./chapter-lookup";
import { CharacterTierBadge } from "./character-tier-badge";
import { RESOLUTION_METHOD_LABEL } from "./character-labels";
import { CharacterRelationships } from "./graph/character-relationships";
import { MentionInspectorDrawer } from "./mention-inspector-drawer";
import { MentionsTimeline } from "./mentions-timeline";
import { bookById, sortedBooks } from "./project-lookup";
import { usePagedMentions } from "./use-paged-mentions";

const Select = chakra("select");
const MENTION_PAGE_SIZE = 100;

const EMPTY_BOOKS: Book[] = [];
const EMPTY_CHAPTERS: Chapter[] = [];

export const CharacterDetail = () => {
  // States.
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedBookId, setSelectedBookId] = useState<string | null>(null);

  // Hooks.
  const { projectId = "", characterId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();

  // Apis.
  const project = useProject(projectId);
  const character = useCharacter(characterId);
  const mentions = usePagedMentions(characterId, {
    pageSize: MENTION_PAGE_SIZE,
    expectedTotal: character.data?.mention_count,
  });

  // Variables.
  const selectedChapter = searchParams.get("chapter");
  const books = useMemo(() => sortedBooks(project.data?.books ?? EMPTY_BOOKS), [project.data]);
  const byId = useMemo(() => bookById(books), [books]);
  const appearances = useMemo(
    () => [...(character.data?.appearances ?? [])].sort((a, b) => (a.series_order ?? Infinity) - (b.series_order ?? Infinity)),
    [character.data?.appearances],
  );
  const activeBookId =
    selectedBookId ?? character.data?.first_book_id ?? appearances[0]?.book_id ?? undefined;
  const chapters = useChapters(activeBookId);

  // useMemos.
  const chapterList = chapters.data ?? EMPTY_CHAPTERS;
  const firstBook = character.data?.first_book_id ? byId.get(character.data.first_book_id) : undefined;
  const maxAppearanceMentions = Math.max(1, ...appearances.map((a) => a.mention_count));
  const strips: AppearanceSlot[] = appearances.map((appearance) => ({
    seriesOrder: appearance.series_order ?? 0,
    intensity: appearance.mention_count / maxAppearanceMentions,
    isFirst: firstBook?.series_order === appearance.series_order,
  }));
  const bookMentions = useMemo(
    () => mentions.mentions.filter((mention) => mention.book_id === activeBookId),
    [mentions.mentions, activeBookId],
  );
  // `CharacterDetailOut.mentions_per_chapter` is aggregated across every book
  // a multi-book character appears in, and chapter numbers reset per book —
  // trusting it here would silently merge book 1's chapter 3 with book 2's
  // chapter 3. Derived client-side, per the selected book's own chapters,
  // instead (SCR-1, plans/sprint-5/SCR.md).
  const histogram = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const mention of bookMentions) {
      const key = chapterKeyForPage(chapterList, mention.page);
      counts[key] = (counts[key] ?? 0) + 1;
    }
    return counts;
  }, [bookMentions, chapterList]);
  const visibleMentions = useMemo(() => {
    if (selectedChapter === null) { return bookMentions; }
    if (chapterList.length === 0) { return bookMentions; }
    return bookMentions.filter(
      (mention) => chapterKeyForPage(chapterList, mention.page) === selectedChapter,
    );
  }, [bookMentions, selectedChapter, chapterList]);

  // Handlers.
  const handleSelectChapter = (chapter: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (chapter === null) {
      next.delete("chapter");
    } else {
      next.set("chapter", chapter);
    }
    setSearchParams(next, { replace: true });
  };

  const handleSelectBook = (bookId: string) => {
    setSelectedBookId(bookId);
    handleSelectChapter(null);
  };

  // Early returns.
  if (character.isPending) {
    return <LoadingSkeleton variant="text" count={6} label="Loading character" />;
  }

  if (character.error) {
    return (
      <ErrorState error={character.error} onRetry={() => void character.refetch()} />
    );
  }

  const data = character.data;
  const activeBook = activeBookId ? byId.get(activeBookId) : undefined;

  return (
    <Stack gap="7">
      <Stack gap="3" borderBottomWidth="1px" borderColor="border" paddingBlockEnd="6">
        <HStack gap="2" textStyle="small" color="fg.subtle">
          <Link asChild>
            <RouterLink to={`/projects/${projectId}/characters`}>Characters</RouterLink>
          </Link>
          <Span>/</Span>
          <Span>{data.canonical_name}</Span>
        </HStack>

        <Heading as="h1" textStyle="display">
          {data.canonical_name}
        </Heading>

        <HStack gap="2.5" wrap="wrap" align="center">
          <CharacterTierBadge tier={data.importance_tier} />
          <Text textStyle="data" color="fg.muted">
            {formatCount(data.mention_count, "mention")}
          </Text>
          {data.first_page !== null && data.first_page !== undefined ? (
            <>
              <Span color="fg.subtle">{"·"}</Span>
              <Text textStyle="small" color="fg.muted">
                first seen
              </Text>
              <PageRef page={data.first_page} bookId={firstBook?.id} bookTitle={firstBook?.title} />
            </>
          ) : null}
        </HStack>

        {books.length > 1 ? (
          <Box maxW="24rem">
            <AppearanceStrip
              totalSlots={books.length}
              slots={strips}
              characterName={data.canonical_name}
              size="md"
            />
          </Box>
        ) : null}
      </Stack>

      <Flex gap="8" align="flex-start" direction={{ base: "column", lg: "row" }}>
        <Stack gap="6" flex="1" minWidth="0">
          {books.length > 1 ? (
            <Stack
              as="section"
              gap="3"
              borderWidth="1px"
              borderColor="border"
              borderRadius="lg"
              bg="bg.surface"
              padding="6"
            >
              <Heading as="h2" textStyle="subheading">
                Appearances
              </Heading>
              <Stack gap="0">
                {appearances.map((appearance) => (
                  <Stack
                    key={appearance.book_id}
                    gap="1.5"
                    borderTopWidth="1px"
                    borderColor="border"
                    paddingBlock="3"
                  >
                    <HStack gap="3" wrap="wrap" justify="space-between">
                      <HStack gap="2.5" wrap="wrap">
                        <Link asChild fontWeight="600">
                          <RouterLink to={`/books/${appearance.book_id}`}>
                            {appearance.series_order !== null ? `${appearance.series_order}. ` : ""}
                            {appearance.book_title}
                          </RouterLink>
                        </Link>
                        {appearances.length === 1 ? (
                          <Text
                            as="span"
                            textStyle="small"
                            color="accent.fg"
                            fontWeight="600"
                            borderWidth="1px"
                            borderStyle="dashed"
                            borderColor="accent.solid"
                            borderRadius="sm"
                            paddingInline="1.5"
                          >
                            new in this book
                          </Text>
                        ) : null}
                      </HStack>
                      <CharacterTierBadge tier={appearance.importance_tier} />
                    </HStack>
                    <HStack gap="3" wrap="wrap" align="baseline">
                      <Text textStyle="data" color="fg.muted">
                        {formatCount(appearance.mention_count, "mention")}
                      </Text>
                      {appearance.first_page !== null && appearance.first_page !== undefined ? (
                        <PageRef
                          page={appearance.first_page}
                          bookId={appearance.book_id}
                          bookTitle={appearance.book_title}
                        />
                      ) : null}
                    </HStack>
                    {(appearance.surface_forms ?? []).length > 0 ? (
                      <Text textStyle="quote" fontStyle="italic" color="fg.muted">
                        {(appearance.surface_forms ?? []).join(" · ")}
                      </Text>
                    ) : null}
                  </Stack>
                ))}
              </Stack>
            </Stack>
          ) : null}

          <Stack
            as="section"
            gap="3"
            borderWidth="1px"
            borderColor="border"
            borderRadius="lg"
            bg="bg.surface"
            padding="6"
          >
            <HStack justify="space-between" align="baseline" wrap="wrap">
              <Heading as="h2" textStyle="subheading">
                Why these are all one person
              </Heading>
              {(data.alias_detail?.length ?? 0) > 0 ? (
                <Button
                  size="sm"
                  variant="outline"
                  borderColor="border.control"
                  color="fg"
                  borderRadius="md"
                  onClick={() => { setDrawerOpen(true); }}
                >
                  Audit every mention
                </Button>
              ) : null}
            </HStack>

            {data.alias_detail && data.alias_detail.length > 0 ? (
              <Stack gap="0">
                {data.alias_detail.map((alias) => (
                  <HStack
                    key={alias.surface_form}
                    gap="3.5"
                    borderTopWidth="1px"
                    borderColor="border"
                    paddingBlock="2.5"
                    wrap="wrap"
                  >
                    <Text textStyle="quote" flex="0 0 12rem">
                      {alias.surface_form}
                    </Text>
                    <Text textStyle="data" color="fg.muted" flex="0 0 4rem" textAlign="right">
                      {alias.count.toLocaleString()}
                    </Text>
                    <Text textStyle="small" color="fg.subtle" flex="1">
                      {RESOLUTION_METHOD_LABEL[alias.resolution_method]}
                      {alias.ambiguous ? (
                        <Span color="status.warn" marginInlineStart="2">
                          ambiguous form
                        </Span>
                      ) : null}
                    </Text>
                  </HStack>
                ))}
              </Stack>
            ) : (
              <Text textStyle="body" color="fg.muted">
                No alias detail yet — this lands with character extraction's
                alias clustering (S3.3/S3.6).
              </Text>
            )}
          </Stack>

          <Stack
            as="section"
            gap="3"
            borderWidth="1px"
            borderColor="border"
            borderRadius="lg"
            bg="bg.surface"
            padding="6"
          >
            <Heading as="h2" textStyle="subheading">
              What the book says
            </Heading>
            {data.attributes && data.attributes.length > 0 ? (
              <Stack gap="0">
                {data.attributes.map((attribute, index) => (
                  <HStack
                    key={`${attribute.label}-${index}`}
                    gap="3.5"
                    borderTopWidth="1px"
                    borderColor="border"
                    paddingBlock="2.5"
                    align="baseline"
                    wrap="wrap"
                  >
                    <Text
                      textStyle="small"
                      color="fg.subtle"
                      fontWeight="600"
                      textTransform="uppercase"
                      letterSpacing="wide"
                      flex="0 0 8rem"
                    >
                      {attribute.label}
                    </Text>
                    <Text textStyle="body" flex="1">
                      {attribute.value}
                    </Text>
                    <PageRef
                      page={attribute.page}
                      bookId={attribute.book_id ?? activeBookId}
                      bookTitle={attribute.book_id ? byId.get(attribute.book_id)?.title : activeBook?.title}
                    />
                  </HStack>
                ))}
              </Stack>
            ) : (
              <Text textStyle="body" color="fg.muted">
                No cited attributes yet.
              </Text>
            )}
          </Stack>

          <Stack
            as="section"
            gap="3"
            borderWidth="1px"
            borderColor="border"
            borderRadius="lg"
            bg="bg.surface"
            padding="6"
          >
            <HStack justify="space-between" align="baseline" wrap="wrap">
              <Heading as="h2" textStyle="subheading">
                Where she appears
              </Heading>
              {appearances.length > 1 ? (
                <HStack gap="2" as="label" alignItems="center">
                  <Text as="span" textStyle="small" color="fg.muted">
                    book
                  </Text>
                  <Select
                    value={activeBookId ?? ""}
                    onChange={(event) => { handleSelectBook(event.target.value); }}
                    textStyle="data"
                    bg="bg.sunken"
                    color="fg"
                    borderWidth="1px"
                    borderColor="border.control"
                    borderRadius="md"
                    paddingInline="2"
                    paddingBlock="1"
                  >
                    {appearances.map((appearance) => (
                      <option key={appearance.book_id} value={appearance.book_id}>
                        {appearance.series_order}. {appearance.book_title}
                      </option>
                    ))}
                  </Select>
                </HStack>
              ) : (
                <Text textStyle="small" color="fg.subtle">
                  mentions per chapter
                </Text>
              )}
            </HStack>
            <MentionsTimeline
              histogram={histogram}
              selectedChapter={selectedChapter}
              onSelectChapter={handleSelectChapter}
            />
          </Stack>

          <Stack
            as="section"
            gap="3"
            borderWidth="1px"
            borderColor="border"
            borderRadius="lg"
            bg="bg.surface"
            padding="6"
          >
            <HStack justify="space-between" align="baseline" wrap="wrap">
              <Heading as="h2" textStyle="subheading">
                Mentions
              </Heading>
              {selectedChapter !== null ? (
                <Button
                  size="sm"
                  variant="ghost"
                  color="accent.fg"
                  onClick={() => { handleSelectChapter(null); }}
                >
                  Clear chapter filter
                </Button>
              ) : null}
            </HStack>

            {mentions.isFirstLoad ? (
              <LoadingSkeleton variant="rows" count={4} label="Loading mentions" />
            ) : null}

            {mentions.error ? <ErrorState error={mentions.error} /> : null}

            {!mentions.isFirstLoad && !mentions.error && visibleMentions.length === 0 ? (
              <Text textStyle="body" color="fg.muted">
                {selectedChapter !== null
                  ? "No mentions loaded yet for this chapter — try loading more."
                  : "No mentions recorded yet for this book."}
              </Text>
            ) : null}

            <Stack gap="0">
              {visibleMentions.map((mention) => (
                <Stack
                  key={mention.id}
                  gap="1"
                  borderTopWidth="1px"
                  borderColor="border"
                  paddingBlock="3"
                >
                  <HStack justify="space-between" wrap="wrap" gap="2">
                    <Text textStyle="quote">{mention.surface_form}</Text>
                    <PageRef page={mention.page} bookId={mention.book_id} bookTitle={activeBook?.title} />
                  </HStack>
                  {mention.context ? (
                    <Text textStyle="small" color="fg.muted" lineClamp={2}>
                      {mention.context}
                    </Text>
                  ) : null}
                </Stack>
              ))}
            </Stack>

            {mentions.canLoadMore ? (
              <Box paddingBlockStart="2">
                <Button
                  size="sm"
                  variant="outline"
                  borderColor="border.control"
                  color="fg"
                  borderRadius="md"
                  loading={mentions.isFetchingMore}
                  onClick={mentions.loadMore}
                >
                  Load more mentions
                </Button>
              </Box>
            ) : null}
          </Stack>
        </Stack>

        <Box width={{ base: "full", lg: "22rem" }} flexShrink="0">
          <Stack
            as="section"
            gap="3"
            borderWidth="1px"
            borderColor="border"
            borderRadius="lg"
            bg="bg.surface"
            padding="6"
          >
            <Heading as="h2" textStyle="subheading">
              Relationships
            </Heading>
            <CharacterRelationships characterId={characterId} projectId={projectId} books={books} />
          </Stack>
        </Box>
      </Flex>

      <MentionInspectorDrawer
        characterId={characterId}
        books={books}
        character={data}
        open={drawerOpen}
        onClose={() => { setDrawerOpen(false); }}
      />
    </Stack>
  );
};

export default CharacterDetail;

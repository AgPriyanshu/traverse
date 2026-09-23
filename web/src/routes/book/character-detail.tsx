import { Box, Button, Flex, HStack, Heading, Link, Span, Stack, Text } from "@chakra-ui/react";
import { useMemo, useState } from "react";
import { Link as RouterLink, useParams, useSearchParams } from "react-router";
import { EmptyState, ErrorState, LoadingSkeleton, PageRef } from "@/components/ui";
import type { Chapter } from "@/lib/api";
import { useBook, useCharacter, useChapters } from "@/lib/api";
import { formatCount } from "@/lib/format";
import { chapterKeyForPage } from "./chapter-lookup";
import { CharacterTierBadge } from "./character-tier-badge";
import { RESOLUTION_METHOD_LABEL } from "./character-labels";
import { MentionInspectorDrawer } from "./mention-inspector-drawer";
import { MentionsTimeline } from "./mentions-timeline";
import { usePagedMentions } from "./use-paged-mentions";

const MENTION_PAGE_SIZE = 100;

// See characters.tsx's `EMPTY_ROSTER` — same reason.
const EMPTY_CHAPTERS: Chapter[] = [];

export const CharacterDetail = () => {
  // States.
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Hooks.
  const { bookId = "", characterId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();

  // Apis.
  const book = useBook(bookId);
  const character = useCharacter(characterId);
  const chapters = useChapters(bookId);
  const mentions = usePagedMentions(characterId, {
    pageSize: MENTION_PAGE_SIZE,
    expectedTotal: character.data?.mention_count,
  });

  // Variables.
  const selectedChapter = searchParams.get("chapter");
  const chapterList = chapters.data ?? EMPTY_CHAPTERS;

  // useMemos.
  const chapterNumbers = useMemo(() => {
    const histogram = character.data?.mentions_per_chapter ?? {};
    return Object.keys(histogram)
      .map(Number)
      .filter((value) => Number.isFinite(value));
  }, [character.data?.mentions_per_chapter]);
  const chapterSpanLabel =
    chapterNumbers.length > 0
      ? `chapters ${Math.min(...chapterNumbers)}–${Math.max(...chapterNumbers)}`
      : null;
  const visibleMentions = useMemo(() => {
    if (selectedChapter === null) { return mentions.mentions; }
    if (chapterList.length === 0) { return mentions.mentions; }
    return mentions.mentions.filter(
      (mention) => chapterKeyForPage(chapterList, mention.page) === selectedChapter,
    );
  }, [mentions.mentions, selectedChapter, chapterList]);

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

  return (
    <Stack gap="7">
      <Stack gap="3" borderBottomWidth="1px" borderColor="border" paddingBlockEnd="6">
        <HStack gap="2" textStyle="small" color="fg.subtle">
          <Link asChild>
            <RouterLink to={`/books/${bookId}/characters`}>Characters</RouterLink>
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
            {chapterSpanLabel ? ` · ${chapterSpanLabel}` : ""}
          </Text>
          {data.first_page !== null && data.first_page !== undefined ? (
            <>
              <Span color="fg.subtle">{"·"}</Span>
              <Text textStyle="small" color="fg.muted">
                first seen
              </Text>
              <PageRef page={data.first_page} bookId={bookId} bookTitle={book.data?.title} />
            </>
          ) : null}
        </HStack>
      </Stack>

      <Flex gap="8" align="flex-start" direction={{ base: "column", lg: "row" }}>
        <Stack gap="6" flex="1" minWidth="0">
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
                    <PageRef page={attribute.page} bookId={bookId} bookTitle={book.data?.title} />
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
            <HStack justify="space-between" align="baseline">
              <Heading as="h2" textStyle="subheading">
                Where she appears
              </Heading>
              <Text textStyle="small" color="fg.subtle">
                mentions per chapter
              </Text>
            </HStack>
            <MentionsTimeline
              histogram={data.mentions_per_chapter ?? {}}
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
                  : "No mentions recorded yet."}
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
                    <PageRef page={mention.page} bookId={bookId} bookTitle={book.data?.title} />
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
            <EmptyState
              title="Coming in Sprint 4"
              description="Traverse will show who this character is connected to here, with the evidence behind every edge — kinship, romantic, social and adversarial."
            />
          </Stack>
        </Box>
      </Flex>

      <MentionInspectorDrawer
        characterId={characterId}
        bookId={bookId}
        bookTitle={book.data?.title}
        character={data}
        open={drawerOpen}
        onClose={() => { setDrawerOpen(false); }}
      />
    </Stack>
  );
};

export default CharacterDetail;

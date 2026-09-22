import { Box, Button, Drawer, HStack, Portal, Span, Stack, Text } from "@chakra-ui/react";
import { useMemo, useState } from "react";
import { ErrorState, LoadingSkeleton, PageRef } from "@/components/ui";
import type { CharacterDetail, Mention } from "@/lib/api";
import { RESOLUTION_METHOD_LABEL } from "./character-labels";
import { usePagedMentions } from "./use-paged-mentions";

const DRAWER_PAGE_SIZE = 200;

export type MentionInspectorDrawerProps = {
  characterId: string;
  bookId: string;
  bookTitle?: string | null;
  character: CharacterDetail;
  open: boolean;
  onClose: () => void;
};

/**
 * The audit view for a merge: every mention grouped by surface form, with
 * `resolution_method` shown as a trust affordance — "why does the system
 * think Lizzy is Elizabeth?" gets an answer, not silence (S3.12).
 */
export const MentionInspectorDrawer = ({
  characterId,
  bookId,
  bookTitle,
  character,
  open,
  onClose,
}: MentionInspectorDrawerProps) => {
  // States.
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());

  // Apis.
  const mentions = usePagedMentions(open ? characterId : undefined, {
    pageSize: DRAWER_PAGE_SIZE,
    expectedTotal: character.mention_count,
  });

  // useMemos.
  const bySurfaceForm = useMemo(() => {
    const map = new Map<string, Mention[]>();
    for (const mention of mentions.mentions) {
      const bucket = map.get(mention.surface_form) ?? [];
      bucket.push(mention);
      map.set(mention.surface_form, bucket);
    }
    return map;
  }, [mentions.mentions]);

  // Handlers.
  const toggle = (surfaceForm: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(surfaceForm)) {
        next.delete(surfaceForm);
      } else {
        next.add(surfaceForm);
      }
      return next;
    });
  };

  const aliases = character.alias_detail ?? [];

  return (
    <Drawer.Root
      open={open}
      placement="end"
      onOpenChange={(details) => {
        if (!details.open) { onClose(); }
      }}
    >
      <Portal>
        <Drawer.Backdrop />
        <Drawer.Positioner>
          <Drawer.Content bg="bg.surface" maxW={{ base: "full", sm: "lg" }}>
            <Drawer.Header borderBottomWidth="1px" borderColor="border">
              <Drawer.Title textStyle="subheading" color="fg">
                Every mention of {character.canonical_name}
              </Drawer.Title>
              <Text textStyle="data" color="fg.subtle">
                {aliases.length} surface forms
                {mentions.mentions.length > 0
                  ? ` · ${mentions.mentions.length.toLocaleString()} of ${character.mention_count.toLocaleString()} loaded`
                  : ""}
              </Text>
            </Drawer.Header>

            <Drawer.Body>
              <Stack gap="0">
                {mentions.isFirstLoad ? (
                  <Box paddingBlock="4">
                    <LoadingSkeleton variant="rows" count={4} label="Loading mentions" />
                  </Box>
                ) : null}

                {mentions.error ? (
                  <Box paddingBlock="4">
                    <ErrorState error={mentions.error} />
                  </Box>
                ) : null}

                {!mentions.isFirstLoad && !mentions.error && aliases.length === 0 ? (
                  <Text textStyle="body" color="fg.muted" paddingBlock="4">
                    No alias detail recorded for this character yet.
                  </Text>
                ) : null}

                {aliases.map((alias) => {
                  const loaded = bySurfaceForm.get(alias.surface_form) ?? [];
                  const isExpanded = expanded.has(alias.surface_form);

                  return (
                    <Box
                      key={alias.surface_form}
                      borderTopWidth="1px"
                      borderColor="border"
                    >
                      <Button
                        variant="ghost"
                        width="full"
                        justifyContent="flex-start"
                        textAlign="left"
                        paddingBlock="3"
                        height="auto"
                        gap="3"
                        fontWeight="400"
                        aria-expanded={isExpanded}
                        onClick={() => { toggle(alias.surface_form); }}
                      >
                        <Text textStyle="quote" flex="1" fontWeight="400">
                          {alias.surface_form}
                        </Text>
                        <Text textStyle="data" color="fg.muted">
                          {alias.count.toLocaleString()}
                        </Text>
                        <Text textStyle="small" color="fg.subtle" minWidth="9rem" textAlign="right">
                          {RESOLUTION_METHOD_LABEL[alias.resolution_method]}
                        </Text>
                      </Button>

                      {isExpanded ? (
                        <Stack gap="0" paddingBlockEnd="3">
                          {loaded.length === 0 ? (
                            <Text textStyle="small" color="fg.subtle" paddingBlock="2">
                              {mentions.canLoadMore || mentions.isFetchingMore
                                ? "Not loaded yet — load more mentions below."
                                : "No individual mentions recorded for this form."}
                            </Text>
                          ) : null}
                          {loaded.map((mention) => (
                            <HStack
                              key={mention.id}
                              gap="3"
                              borderTopWidth="1px"
                              borderColor="border"
                              paddingBlock="2"
                              align="baseline"
                              wrap="wrap"
                            >
                              <PageRef page={mention.page} bookId={bookId} bookTitle={bookTitle} />
                              {mention.context ? (
                                <Text textStyle="small" color="fg.muted" flex="1" lineClamp={2}>
                                  {mention.context}
                                </Text>
                              ) : null}
                              <Span textStyle="data" color="fg.subtle">
                                {RESOLUTION_METHOD_LABEL[mention.resolution_method]}
                              </Span>
                            </HStack>
                          ))}
                        </Stack>
                      ) : null}
                    </Box>
                  );
                })}

                {mentions.canLoadMore ? (
                  <Box paddingBlockStart="4">
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
            </Drawer.Body>

            <Drawer.CloseTrigger asChild>
              <Button
                size="sm"
                variant="ghost"
                position="absolute"
                top="3"
                right="3"
                color="fg.muted"
                onClick={onClose}
              >
                Close
              </Button>
            </Drawer.CloseTrigger>
          </Drawer.Content>
        </Drawer.Positioner>
      </Portal>
    </Drawer.Root>
  );
};

export default MentionInspectorDrawer;

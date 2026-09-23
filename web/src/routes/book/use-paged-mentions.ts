import { useQueries } from "@tanstack/react-query";
import { useState } from "react";
import { mentionsQueryOptions } from "@/lib/api";

const DEFAULT_PAGE_SIZE = 200;

export type UsePagedMentionsOptions = {
  pageSize?: number;
  /** `character.mention_count` — stop paging once we have at least this many, same idea as the chunk inspector's `chunk_count` stop condition. */
  expectedTotal?: number;
};

/**
 * Incrementally pages `GET /characters/{id}/mentions` and accumulates the
 * results, the same shape as `chunk-inspector.tsx`'s own manual pagination —
 * a character can carry 1,000+ mentions (Elizabeth Bennet: 1,142), so the
 * mention list and the audit drawer both need "load more", not one giant
 * fetch.
 */
export const usePagedMentions = (
  characterId: string | undefined,
  { pageSize = DEFAULT_PAGE_SIZE, expectedTotal }: UsePagedMentionsOptions = {},
) => {
  // States.
  const [pageCount, setPageCount] = useState(1);
  // Not an effect — React's own render-phase pattern for resetting state when
  // a prop changes (see chunk-inspector.tsx / page-viewer.tsx).
  const [trackedId, setTrackedId] = useState(characterId);
  if (characterId !== trackedId) {
    setTrackedId(characterId);
    setPageCount(1);
  }

  // Apis.
  const pages = useQueries({
    queries: characterId
      ? Array.from({ length: pageCount }, (_unused, index) => ({
          ...mentionsQueryOptions(characterId, {
            limit: pageSize,
            offset: index * pageSize,
          }),
        }))
      : [],
  });

  // Variables.
  const isFirstLoad = pages.length > 0 && pages[0].isPending;
  const isFetchingMore = pages.some((page) => page.isFetching);
  const error = pages.find((page) => page.error)?.error;
  const lastPage = pages[pages.length - 1];
  const mentions = pages.flatMap((page) => page.data ?? []);
  const fetchedEverything =
    lastPage?.data !== undefined && lastPage.data.length < pageSize;
  const hasExpectedTotal =
    expectedTotal !== undefined && mentions.length >= expectedTotal;
  const canLoadMore =
    !fetchedEverything && !hasExpectedTotal && !isFirstLoad && !error;

  return {
    mentions,
    isFirstLoad,
    isFetchingMore,
    error,
    canLoadMore,
    loadMore: () => { setPageCount((current) => current + 1); },
  };
};

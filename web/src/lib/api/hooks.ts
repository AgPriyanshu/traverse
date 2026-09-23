import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";
import { client, request } from "./client";
import { queryKeys } from "./query-keys";
import type {
  AlreadyIngestedOut,
  Book,
  ProjectCreate,
  QueryParams,
  ReviewResolution,
  RoutingPolicy,
  Schemas,
} from "./types";
import { isAlreadyIngested, isTerminalStatus } from "./types";
import type { UploadProgress } from "./upload";
import { uploadMultipart } from "./upload";

const POLL_INTERVAL_MS = 2000;
const SLOW_POLL_INTERVAL_MS = 10_000;
const SLOW_POLL_AFTER_MS = 5 * 60 * 1000;

// --- Projects ---------------------------------------------------------------

export const useProjects = () => {
  return useQuery({
    queryKey: queryKeys.projects(),
    queryFn: () => request(() => client.GET("/api/projects")),
  });
};

export const useProject = (projectId: string | undefined) => {
  return useQuery({
    queryKey: queryKeys.project(projectId ?? ""),
    queryFn: () =>
      request(() =>
        client.GET("/api/projects/{project_id}", {
          params: { path: { project_id: projectId as string } },
        }),
      ),
    enabled: Boolean(projectId),
  });
};

export const useCreateProject = () => {
  // Apis.
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: ProjectCreate) =>
      request(() => client.POST("/api/projects", { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects() });
    },
  });
};

export const useReorderBooks = (projectId: string) => {
  // Apis.
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: Schemas["BookOrderUpdate"]) =>
      request(() =>
        client.PATCH("/api/projects/{project_id}/order", {
          params: { path: { project_id: projectId } },
          body,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.project(projectId),
      });
    },
  });
};

// --- Books ------------------------------------------------------------------

type BooksParams = QueryParams<"/api/books", "get">;

/** The library across every project — one call, filterable by project or status. */
export const useBooks = (params?: BooksParams) => {
  return useQuery({
    queryKey: queryKeys.books(params),
    queryFn: () =>
      request(() => client.GET("/api/books", { params: { query: params } })),
  });
};

export type UploadBookInput = {
  projectId: string;
  file: File;
  seriesOrder?: number;
  /** Real percentages from `XMLHttpRequest.upload` — `fetch` cannot report this. */
  onProgress?: (progress: UploadProgress) => void;
  signal?: AbortSignal;
};

export type UploadBookResult = Book | AlreadyIngestedOut;

/**
 * Goes around the typed `openapi-fetch` client — see `upload.ts` — so the
 * upload can report real progress. The `200` "already ingested" response
 * (SCR-10) is not yet in the generated contract; callers narrow the result
 * with `isAlreadyIngested`.
 */
export const useUploadBook = () => {
  // Apis.
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      projectId,
      file,
      seriesOrder,
      onProgress,
      signal,
    }: UploadBookInput) => {
      const form = new FormData();
      form.append("file", file);
      return uploadMultipart<UploadBookResult>({
        path: `/api/projects/${projectId}/books`,
        query: { series_order: seriesOrder ?? null },
        form,
        onProgress,
        signal,
      });
    },
    onSuccess: (result, { projectId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects() });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.project(
          isAlreadyIngested(result) ? projectId : result.project_id,
        ),
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.books() });
    },
  });
};

export const useBook = (bookId: string | undefined) => {
  return useQuery({
    queryKey: queryKeys.book(bookId ?? ""),
    queryFn: () =>
      request(() =>
        client.GET("/api/books/{book_id}", {
          params: { path: { book_id: bookId as string } },
        }),
      ),
    enabled: Boolean(bookId),
  });
};

export const useBookStatus = (bookId: string | undefined) => {
  // Refs.
  // Tracks when polling started for *this* book, so a long-open tab backs off
  // to a slower interval rather than hammering the API for the life of the
  // page (S2.12). Keyed on bookId so navigating to a different book restarts
  // the clock instead of inheriting the previous book's elapsed time.
  const pollStartRef = useRef<{ bookId: string; at: number } | null>(null);

  return useQuery({
    queryKey: queryKeys.bookStatus(bookId ?? ""),
    queryFn: () =>
      request(() =>
        client.GET("/api/books/{book_id}/status", {
          params: { path: { book_id: bookId as string } },
        }),
      ),
    enabled: Boolean(bookId),
    // Stops dead on a terminal status. A poll with no stop condition is a
    // background CPU leak in a tab somebody left open.
    refetchInterval: (query) => {
      if (!bookId || query.state.error) { return false; }
      if (isTerminalStatus(query.state.data?.status)) { return false; }

      if (pollStartRef.current?.bookId !== bookId) {
        pollStartRef.current = { bookId, at: Date.now() };
      }
      const elapsed = Date.now() - pollStartRef.current.at;
      return elapsed > SLOW_POLL_AFTER_MS ? SLOW_POLL_INTERVAL_MS : POLL_INTERVAL_MS;
    },
  });
};

export const useDeleteBook = () => {
  // Apis.
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (bookId: string) =>
      request(() =>
        client.DELETE("/api/books/{book_id}", {
          params: { path: { book_id: bookId } },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.books() });
    },
  });
};

export const useReprocessBook = (bookId: string) => {
  // Apis.
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (fromStage?: string) =>
      request(() =>
        client.POST("/api/books/{book_id}/reprocess", {
          params: {
            path: { book_id: bookId },
            query: { from_stage: fromStage ?? null },
          },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.bookStatus(bookId),
      });
    },
  });
};

export const useChapters = (bookId: string | undefined) => {
  return useQuery({
    queryKey: queryKeys.bookChapters(bookId ?? ""),
    queryFn: () =>
      request(() =>
        client.GET("/api/books/{book_id}/chapters", {
          params: { path: { book_id: bookId as string } },
        }),
      ),
    enabled: Boolean(bookId),
  });
};

export type ChunksParams = QueryParams<"/api/books/{book_id}/chunks", "get">;

/**
 * Shared with the chunk inspector's manual pagination (`useQueries` over
 * several offsets at once), so that "load one more page" is one more query
 * object rather than a second copy of this fetch.
 */
export const chunksQueryOptions = (bookId: string, params?: ChunksParams) => ({
  queryKey: queryKeys.bookChunks(bookId, params),
  queryFn: () =>
    request(() =>
      client.GET("/api/books/{book_id}/chunks", {
        params: { path: { book_id: bookId }, query: params },
      }),
    ),
});

export const useChunks = (
  bookId: string | undefined,
  params?: ChunksParams,
) => {
  return useQuery({
    ...chunksQueryOptions(bookId ?? "", params),
    enabled: Boolean(bookId),
  });
};

/**
 * Shared with the page viewer's neighbour prefetch (`queryClient.prefetchQuery`
 * for page ± 1), so a page it will probably need next is already warm without
 * a second copy of this fetch.
 */
export const pageRenderQueryOptions = (bookId: string, page: number) => ({
  queryKey: queryKeys.bookPage(bookId, page),
  queryFn: () =>
    request(() =>
      client.GET("/api/books/{book_id}/pages/{page}", {
        params: { path: { book_id: bookId, page } },
      }),
    ),
});

export const usePageRender = (
  bookId: string | undefined,
  page: number | undefined,
) => {
  return useQuery({
    ...pageRenderQueryOptions(bookId ?? "", page ?? 0),
    enabled: Boolean(bookId) && page !== undefined,
  });
};

// --- Characters -------------------------------------------------------------

type CharactersParams = QueryParams<
  "/api/projects/{project_id}/characters",
  "get"
>;

export const useCharacters = (
  projectId: string | undefined,
  params?: CharactersParams,
) => {
  return useQuery({
    queryKey: queryKeys.projectCharacters(projectId ?? "", params),
    queryFn: () =>
      request(() =>
        client.GET("/api/projects/{project_id}/characters", {
          params: { path: { project_id: projectId as string }, query: params },
        }),
      ),
    enabled: Boolean(projectId),
  });
};

export const useCharacter = (characterId: string | undefined) => {
  return useQuery({
    queryKey: queryKeys.character(characterId ?? ""),
    queryFn: () =>
      request(() =>
        client.GET("/api/characters/{character_id}", {
          params: { path: { character_id: characterId as string } },
        }),
      ),
    enabled: Boolean(characterId),
  });
};

export type MentionsParams = QueryParams<
  "/api/characters/{character_id}/mentions",
  "get"
>;

/**
 * Shared with the character detail page's and the alias/mention inspector
 * drawer's own incremental pagination (`useQueries` over several offsets at
 * once) — same shape as `chunksQueryOptions` for the same reason: one page is
 * as far as `useMentions` goes, but auditing a character with 1,000+ mentions
 * needs several pages fetched and accumulated client-side.
 */
export const mentionsQueryOptions = (characterId: string, params?: MentionsParams) => ({
  queryKey: queryKeys.characterMentions(characterId, params),
  queryFn: () =>
    request(() =>
      client.GET("/api/characters/{character_id}/mentions", {
        params: { path: { character_id: characterId }, query: params },
      }),
    ),
});

export const useMentions = (
  characterId: string | undefined,
  params?: MentionsParams,
) => {
  return useQuery({
    ...mentionsQueryOptions(characterId ?? "", params),
    enabled: Boolean(characterId),
  });
};

export const useAppearances = (characterId: string | undefined) => {
  return useQuery({
    queryKey: queryKeys.characterAppearances(characterId ?? ""),
    queryFn: () =>
      request(() =>
        client.GET("/api/characters/{character_id}/appearances", {
          params: { path: { character_id: characterId as string } },
        }),
      ),
    enabled: Boolean(characterId),
  });
};

export const useMergeCharacters = () => {
  // Apis.
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: Schemas["CharacterMergeRequest"]) =>
      request(() => client.POST("/api/characters/merge", { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.characters() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects() });
    },
  });
};

export const useSplitCharacter = (characterId: string) => {
  // Apis.
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: Schemas["CharacterSplitRequest"]) =>
      request(() =>
        client.POST("/api/characters/{character_id}/split", {
          params: { path: { character_id: characterId } },
          body,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.characters() });
    },
  });
};

// --- Graph ------------------------------------------------------------------

export const useOntology = () => {
  return useQuery({
    queryKey: queryKeys.ontology(),
    queryFn: () => request(() => client.GET("/api/graph/ontology")),
    staleTime: Infinity,
  });
};

type GraphParams = QueryParams<"/api/projects/{project_id}/graph", "get">;

export const useProjectGraph = (
  projectId: string | undefined,
  params?: GraphParams,
) => {
  return useQuery({
    queryKey: queryKeys.projectGraph(projectId ?? "", params),
    queryFn: () =>
      request(() =>
        client.GET("/api/projects/{project_id}/graph", {
          params: { path: { project_id: projectId as string }, query: params },
        }),
      ),
    enabled: Boolean(projectId),
  });
};

export const useNeighbourhood = (
  characterId: string | undefined,
  depth: 1 | 2 = 1,
) => {
  return useQuery({
    queryKey: queryKeys.characterNeighbourhood(characterId ?? "", depth),
    queryFn: () =>
      request(() =>
        client.GET("/api/characters/{character_id}/neighbourhood", {
          params: {
            path: { character_id: characterId as string },
            query: { depth },
          },
        }),
      ),
    enabled: Boolean(characterId),
  });
};

type EvidenceParams = QueryParams<
  "/api/relations/{relation_id}/evidence",
  "get"
>;

export const useEvidence = (
  relationId: string | undefined,
  params?: EvidenceParams,
) => {
  return useQuery({
    queryKey: queryKeys.relationEvidence(relationId ?? "", params),
    queryFn: () =>
      request(() =>
        client.GET("/api/relations/{relation_id}/evidence", {
          params: {
            path: { relation_id: relationId as string },
            query: params,
          },
        }),
      ),
    enabled: Boolean(relationId),
  });
};

export const useRelationArc = (a: string | undefined, b: string | undefined) => {
  return useQuery({
    queryKey: queryKeys.relationArc(a ?? "", b ?? ""),
    queryFn: () =>
      request(() =>
        client.GET("/api/relations/arc", {
          params: { query: { a: a as string, b: b as string } },
        }),
      ),
    enabled: Boolean(a) && Boolean(b),
  });
};

export const useGraphPath = (
  from: string | undefined,
  to: string | undefined,
  maxHops = 4,
) => {
  return useQuery({
    queryKey: queryKeys.graphPath(from ?? "", to ?? "", maxHops),
    queryFn: () =>
      request(() =>
        client.GET("/api/graph/path", {
          params: {
            query: { from: from as string, to: to as string, max_hops: maxHops },
          },
        }),
      ),
    enabled: Boolean(from) && Boolean(to),
  });
};

// --- Search and review ------------------------------------------------------

type SearchParams = NonNullable<QueryParams<"/api/search", "get">>;

export const useSearch = (params: SearchParams | undefined) => {
  return useQuery({
    queryKey: queryKeys.search(params),
    queryFn: () =>
      request(() =>
        client.GET("/api/search", { params: { query: params as SearchParams } }),
      ),
    enabled: Boolean(params?.project_id) && Boolean(params?.q),
  });
};

type ReviewTasksParams = QueryParams<"/api/review/tasks", "get">;

export const useReviewTasks = (params?: ReviewTasksParams) => {
  return useQuery({
    queryKey: queryKeys.reviewTasks(params),
    queryFn: () =>
      request(() =>
        client.GET("/api/review/tasks", { params: { query: params } }),
      ),
  });
};

export const useResolveReviewTask = () => {
  // Apis.
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      taskId,
      resolution,
    }: {
      taskId: string;
      resolution: ReviewResolution;
    }) =>
      request(() =>
        client.POST("/api/review/tasks/{task_id}/resolve", {
          params: { path: { task_id: taskId } },
          body: resolution,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["review", "tasks"] });
    },
  });
};

// --- Ops --------------------------------------------------------------------

export const useHealth = () => {
  return useQuery({
    queryKey: queryKeys.health(),
    queryFn: () => request(() => client.GET("/api/health")),
    refetchInterval: 30_000,
    retry: false,
  });
};

type MetricsParams = QueryParams<"/api/ops/metrics", "get">;

export const useMetrics = (params?: MetricsParams) => {
  return useQuery({
    queryKey: queryKeys.metrics(params),
    queryFn: () =>
      request(() =>
        client.GET("/api/ops/metrics", { params: { query: params } }),
      ),
  });
};

type PipelineRunsParams = QueryParams<"/api/ops/pipeline/runs", "get">;

export const usePipelineRuns = (params?: PipelineRunsParams) => {
  return useQuery({
    queryKey: queryKeys.pipelineRuns(params),
    queryFn: () =>
      request(() =>
        client.GET("/api/ops/pipeline/runs", { params: { query: params } }),
      ),
  });
};

export const useDeadLetter = () => {
  return useQuery({
    queryKey: queryKeys.deadLetter(),
    queryFn: () => request(() => client.GET("/api/ops/pipeline/dead-letter")),
  });
};

export const useRoutingPolicy = () => {
  return useQuery({
    queryKey: queryKeys.routingPolicy(),
    queryFn: () => request(() => client.GET("/api/ops/routing-policy")),
  });
};

export const useSetRoutingPolicy = () => {
  // Apis.
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: RoutingPolicy) =>
      request(() => client.PUT("/api/ops/routing-policy", { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.routingPolicy(),
      });
    },
  });
};

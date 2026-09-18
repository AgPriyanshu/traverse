import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { client, request } from "./client";
import { queryKeys } from "./query-keys";
import type {
  ProjectCreate,
  QueryParams,
  ReviewResolution,
  RoutingPolicy,
  Schemas,
} from "./types";
import { isTerminalStatus } from "./types";

const POLL_INTERVAL_MS = 2000;

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
};

export const useUploadBook = () => {
  // Apis.
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ projectId, file, seriesOrder }: UploadBookInput) =>
      request(() =>
        client.POST("/api/projects/{project_id}/books", {
          params: {
            path: { project_id: projectId },
            query: { series_order: seriesOrder ?? null },
          },
          // The contract types a binary part as `string`; the wire wants the
          // File itself, so the serialiser below is what actually runs.
          body: { file: file as unknown as string },
          bodySerializer: (body: { file: unknown }) => {
            const form = new FormData();
            form.append("file", body.file as File);
            return form;
          },
        }),
      ),
    onSuccess: (book) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects() });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.project(book.project_id),
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
      if (query.state.error) { return false; }
      return isTerminalStatus(query.state.data?.status)
        ? false
        : POLL_INTERVAL_MS;
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

type ChunksParams = QueryParams<"/api/books/{book_id}/chunks", "get">;

export const useChunks = (
  bookId: string | undefined,
  params?: ChunksParams,
) => {
  return useQuery({
    queryKey: queryKeys.bookChunks(bookId ?? "", params),
    queryFn: () =>
      request(() =>
        client.GET("/api/books/{book_id}/chunks", {
          params: { path: { book_id: bookId as string }, query: params },
        }),
      ),
    enabled: Boolean(bookId),
  });
};

export const usePageRender = (
  bookId: string | undefined,
  page: number | undefined,
) => {
  return useQuery({
    queryKey: queryKeys.bookPage(bookId ?? "", page ?? 0),
    queryFn: () =>
      request(() =>
        client.GET("/api/books/{book_id}/pages/{page}", {
          params: { path: { book_id: bookId as string, page: page as number } },
        }),
      ),
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

type MentionsParams = QueryParams<
  "/api/characters/{character_id}/mentions",
  "get"
>;

export const useMentions = (
  characterId: string | undefined,
  params?: MentionsParams,
) => {
  return useQuery({
    queryKey: queryKeys.characterMentions(characterId ?? "", params),
    queryFn: () =>
      request(() =>
        client.GET("/api/characters/{character_id}/mentions", {
          params: {
            path: { character_id: characterId as string },
            query: params,
          },
        }),
      ),
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

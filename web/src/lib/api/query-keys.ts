type Params = Record<string, unknown> | undefined;

/**
 * One factory, so an invalidation can never miss a key that was spelled
 * differently at the call site.
 */
export const queryKeys = {
  health: () => ["health"] as const,

  projects: () => ["projects"] as const,
  project: (projectId: string) => ["projects", projectId] as const,
  projectCharacters: (projectId: string, params?: Params) =>
    ["projects", projectId, "characters", params ?? {}] as const,
  projectGraph: (projectId: string, params?: Params) =>
    ["projects", projectId, "graph", params ?? {}] as const,

  books: (params?: Params) => ["books", params ?? {}] as const,
  book: (bookId: string) => ["books", bookId] as const,
  bookStatus: (bookId: string) => ["books", bookId, "status"] as const,
  bookChapters: (bookId: string) => ["books", bookId, "chapters"] as const,
  bookChunks: (bookId: string, params?: Params) =>
    ["books", bookId, "chunks", params ?? {}] as const,
  bookPage: (bookId: string, page: number) =>
    ["books", bookId, "pages", page] as const,

  characters: () => ["characters"] as const,
  character: (characterId: string, params?: Params) =>
    ["characters", characterId, params ?? {}] as const,
  characterMentions: (characterId: string, params?: Params) =>
    ["characters", characterId, "mentions", params ?? {}] as const,
  characterAppearances: (characterId: string, params?: Params) =>
    ["characters", characterId, "appearances", params ?? {}] as const,
  characterNeighbourhood: (characterId: string, depth: number, params?: Params) =>
    ["characters", characterId, "neighbourhood", depth, params ?? {}] as const,

  ontology: () => ["ontology"] as const,
  relationEvidence: (relationId: string, params?: Params) =>
    ["relations", relationId, "evidence", params ?? {}] as const,
  relationArc: (a: string, b: string, params?: Params) =>
    ["relations", "arc", a, b, params ?? {}] as const,
  graphPath: (from: string, to: string, maxHops: number, params?: Params) =>
    ["graph", "path", from, to, maxHops, params ?? {}] as const,

  search: (params: Params) => ["search", params ?? {}] as const,

  reviewTasks: (params?: Params) => ["review", "tasks", params ?? {}] as const,

  metrics: (params?: Params) => ["ops", "metrics", params ?? {}] as const,
  pipelineRuns: (params?: Params) => ["ops", "runs", params ?? {}] as const,
  deadLetter: () => ["ops", "dead-letter"] as const,
  routingPolicy: () => ["ops", "routing-policy"] as const,
  queryLatency: (projectId: string) =>
    ["ops", "query-latency", projectId] as const,
  reviewAlerts: (params?: Params) =>
    ["ops", "review-alerts", params ?? {}] as const,
  evalRunLatest: () => ["ops", "eval-runs", "latest"] as const,
} as const;

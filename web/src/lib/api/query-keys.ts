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
  character: (characterId: string) => ["characters", characterId] as const,
  characterMentions: (characterId: string, params?: Params) =>
    ["characters", characterId, "mentions", params ?? {}] as const,
  characterAppearances: (characterId: string) =>
    ["characters", characterId, "appearances"] as const,
  characterNeighbourhood: (characterId: string, depth: number) =>
    ["characters", characterId, "neighbourhood", depth] as const,

  ontology: () => ["ontology"] as const,
  relationEvidence: (relationId: string, params?: Params) =>
    ["relations", relationId, "evidence", params ?? {}] as const,
  relationArc: (a: string, b: string) => ["relations", "arc", a, b] as const,
  graphPath: (from: string, to: string, maxHops: number) =>
    ["graph", "path", from, to, maxHops] as const,

  search: (params: Params) => ["search", params ?? {}] as const,

  reviewTasks: (params?: Params) => ["review", "tasks", params ?? {}] as const,

  metrics: (params?: Params) => ["ops", "metrics", params ?? {}] as const,
  pipelineRuns: (params?: Params) => ["ops", "runs", params ?? {}] as const,
  deadLetter: () => ["ops", "dead-letter"] as const,
  routingPolicy: () => ["ops", "routing-policy"] as const,
} as const;

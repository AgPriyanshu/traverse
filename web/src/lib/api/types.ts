import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

export type Project = Schemas["ProjectOut"];
export type ProjectDetail = Schemas["ProjectDetailOut"];
export type ProjectKind = Schemas["ProjectKind"];
export type ProjectCreate = Schemas["ProjectCreate"];

export type Book = Schemas["BookOut"];
export type BookStatus = Schemas["BookStatus"];
export type BookStatusDetail = Schemas["BookStatusOut"];
export type StageStatus = Schemas["StageStatus"];
export type StageName = Schemas["StageName"];
export type StageState = Schemas["StageState"];

export type Chapter = Schemas["ChapterOut"];
export type Chunk = Schemas["ChunkOut"];
export type PageRender = Schemas["PageRenderOut"];
export type SpanBox = Schemas["SpanBox"];

export type Character = Schemas["CharacterOut"];
export type CharacterDetail = Schemas["CharacterDetailOut"];
export type Alias = Schemas["AliasOut"];
export type Mention = Schemas["MentionOut"];
export type Appearance = Schemas["AppearanceOut"];
export type ImportanceTier = Schemas["ImportanceTier"];

export type Graph = Schemas["GraphOut"];
export type GraphNode = Schemas["GraphNodeOut"];
export type GraphEdge = Schemas["GraphEdgeOut"];
export type GraphPath = Schemas["GraphPathOut"];
export type Ontology = Schemas["OntologyOut"];
export type Relation = Schemas["RelationOut"];
export type RelationArc = Schemas["RelationArcOut"];
export type RelationFamily = Schemas["RelationFamily"];
export type Evidence = Schemas["EvidenceOut"];
export type AssertionType = Schemas["AssertionType"];

export type Citation = Schemas["CitationOut"];
export type SearchResult = Schemas["SearchResultOut"];
export type QueryRequest = Schemas["QueryRequest"];
export type QueryEvent = Schemas["QueryEventEnvelope"]["event"];

export type ReviewTask = Schemas["ReviewTaskOut"];
export type ReviewTaskType = Schemas["ReviewTaskType"];
export type ReviewStatus = Schemas["ReviewStatus"];
export type ReviewResolution = Schemas["ReviewResolution"];

export type Health = Schemas["HealthOut"];
export type DependencyHealth = Schemas["DependencyHealth"];
export type Metrics = Schemas["MetricsOut"];
export type IngestionRun = Schemas["IngestionRunOut"];
export type DeadLetter = Schemas["DeadLetterOut"];
export type RoutingPolicy = Schemas["RoutingPolicyOut"];

/** The query-string parameters the contract declares for one operation. */
export type QueryParams<
  P extends keyof paths,
  M extends keyof paths[P],
> = paths[P][M] extends { parameters: { query?: infer Q } } ? Q : never;

/**
 * A book stops changing at these. Anything polling a book's progress must
 * stop here — an ingestion poll that never stops is a CPU leak in an open tab.
 */
const TERMINAL_BOOK_STATUSES: readonly BookStatus[] = ["ready", "failed"];

export const isTerminalStatus = (status: BookStatus | undefined): boolean => {
  if (status === undefined) { return false; }
  return TERMINAL_BOOK_STATUSES.includes(status);
};

/** The frozen ingestion stages, in the order they run. */
export const STAGE_ORDER: readonly StageName[] = [
  "pipeline.parse_and_chunk",
  "pipeline.segment_chapters",
  "pipeline.embed_chunks",
  "pipeline.extract_characters",
  "pipeline.resolve_aliases",
  "pipeline.reconcile_characters",
  "relations.extract",
  "relations.aggregate",
  "graph.upsert",
];

export const STAGE_LABELS: Record<StageName, string> = {
  "pipeline.parse_and_chunk": "Parse and chunk",
  "pipeline.segment_chapters": "Segment chapters",
  "pipeline.embed_chunks": "Embed chunks",
  "pipeline.extract_characters": "Extract characters",
  "pipeline.resolve_aliases": "Resolve aliases",
  "pipeline.reconcile_characters": "Reconcile across books",
  "relations.extract": "Extract relationships",
  "relations.aggregate": "Aggregate relationships",
  "graph.upsert": "Write the graph",
};

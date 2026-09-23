import type {
  Chapter,
  Graph,
  GraphEdge,
  GraphNode,
  ImportanceTier,
  RelationFamily,
} from "@/lib/api";
import { chapterForPage } from "../chapter-lookup";
import { TIER_ORDER } from "../character-labels";
import { FAMILY_ORDER } from "./relation-style";

export type GraphFilters = {
  /** Empty means every family. */
  families: RelationFamily[];
  /** Empty means every tier. */
  tiers: ImportanceTier[];
  minConfidence: number;
  chapterFrom: number | null;
  chapterTo: number | null;
};

export const DEFAULT_FILTERS: GraphFilters = {
  families: [],
  tiers: [],
  minConfidence: 0,
  chapterFrom: null,
  chapterTo: null,
};

const parseList = <T extends string>(raw: string | null, allowed: readonly T[]): T[] => {
  if (!raw) { return []; }
  return raw.split(",").filter((item): item is T => (allowed as readonly string[]).includes(item));
};

const parseNumber = (raw: string | null): number | null => {
  if (raw === null || raw === "") { return null; }
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
};

/** Every filter lives in the URL so a filtered view is a shareable link. */
export const parseFilters = (params: URLSearchParams): GraphFilters => {
  const confidence = parseNumber(params.get("conf")) ?? 0;
  return {
    families: parseList(params.get("family"), FAMILY_ORDER),
    tiers: parseList(params.get("tier"), TIER_ORDER),
    minConfidence: Math.min(1, Math.max(0, confidence)),
    chapterFrom: parseNumber(params.get("from")),
    chapterTo: parseNumber(params.get("to")),
  };
};

export const writeFilters = (
  params: URLSearchParams,
  filters: GraphFilters,
): URLSearchParams => {
  const next = new URLSearchParams(params);
  const set = (key: string, value: string | null) => {
    if (value === null || value === "") {
      next.delete(key);
    } else {
      next.set(key, value);
    }
  };
  set("family", filters.families.length > 0 ? filters.families.join(",") : null);
  set("tier", filters.tiers.length > 0 ? filters.tiers.join(",") : null);
  set("conf", filters.minConfidence > 0 ? String(filters.minConfidence) : null);
  set("from", filters.chapterFrom === null ? null : String(filters.chapterFrom));
  set("to", filters.chapterTo === null ? null : String(filters.chapterTo));
  return next;
};

export const hasEdgeFilter = (filters: GraphFilters): boolean => {
  return (
    filters.families.length > 0 ||
    filters.minConfidence > 0 ||
    filters.chapterFrom !== null ||
    filters.chapterTo !== null
  );
};

/** Edges carry page refs, not chapters, so the chapter comes from the same page-to-chapter join the mention list uses. */
export const edgeChapters = (edge: GraphEdge, chapters: readonly Chapter[]): number[] => {
  const numbers = new Set<number>();
  for (const ref of edge.page_refs ?? []) {
    const chapter = chapterForPage(chapters, ref.page);
    if (chapter?.number !== null && chapter?.number !== undefined) {
      numbers.add(chapter.number);
    }
  }
  return [...numbers].sort((a, b) => a - b);
};

export const edgeChapterSpan = (
  edge: GraphEdge,
  chapters: readonly Chapter[],
): { first: number; last: number } | null => {
  const numbers = edgeChapters(edge, chapters);
  if (numbers.length === 0) { return null; }
  return { first: numbers[0] as number, last: numbers[numbers.length - 1] as number };
};

export type FilteredGraph = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export const filterGraph = (
  graph: Graph,
  filters: GraphFilters,
  chapters: readonly Chapter[],
): FilteredGraph => {
  const nodes = graph.nodes ?? [];
  const edges = graph.edges ?? [];
  const tierOk = new Map<string, boolean>();
  for (const node of nodes) {
    tierOk.set(
      node.id,
      filters.tiers.length === 0 || filters.tiers.includes(node.importance_tier),
    );
  }

  const hasRange = filters.chapterFrom !== null || filters.chapterTo !== null;
  const visibleEdges = edges.filter((edge) => {
    if (!tierOk.get(edge.source) || !tierOk.get(edge.target)) { return false; }
    if (filters.families.length > 0 && !filters.families.includes(edge.family)) { return false; }
    if (edge.confidence < filters.minConfidence) { return false; }
    if (hasRange) {
      const numbers = edgeChapters(edge, chapters);
      const from = filters.chapterFrom ?? -Infinity;
      const to = filters.chapterTo ?? Infinity;
      return numbers.some((number) => number >= from && number <= to);
    }
    return true;
  });

  const connected = new Set<string>();
  for (const edge of visibleEdges) {
    connected.add(edge.source);
    connected.add(edge.target);
  }
  const narrowed = hasEdgeFilter(filters);
  const visibleNodes = nodes.filter(
    (node) => tierOk.get(node.id) && (!narrowed || connected.has(node.id)),
  );

  return { nodes: visibleNodes, edges: visibleEdges };
};

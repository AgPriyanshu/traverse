import type { Graph, GraphEdge, GraphNode, ImportanceTier, RelationFamily } from "@/lib/api";
import { TIER_ORDER } from "../character-labels";
import { FAMILY_ORDER } from "./relation-style";

export type GraphFilters = {
  /** Empty means every family. */
  families: RelationFamily[];
  /** Empty means every tier. */
  tiers: ImportanceTier[];
  minConfidence: number;
  /** A `series_order` to slice the standing graph to one book, client-side — the animation between slices is the feature (S5.11). `null` means every book. */
  bookFilter: number | null;
};

export const DEFAULT_FILTERS: GraphFilters = {
  families: [],
  tiers: [],
  minConfidence: 0,
  bookFilter: null,
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
    bookFilter: parseNumber(params.get("book")),
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
  set("book", filters.bookFilter === null ? null : String(filters.bookFilter));
  return next;
};

export const hasEdgeFilter = (filters: GraphFilters): boolean => {
  return (
    filters.families.length > 0 ||
    filters.minConfidence > 0 ||
    filters.bookFilter !== null
  );
};

/**
 * The distinct books an edge has evidence in, from its own page refs — no
 * join against a book's chapter list is needed at this level of detail. The
 * exact chapter and page live one level down, in the evidence panel and the
 * relationship arc, both of which already carry `chapter_no` per item.
 */
export const edgeBookOrders = (edge: GraphEdge): number[] => {
  const numbers = new Set<number>();
  for (const ref of edge.page_refs ?? []) {
    numbers.add(ref.book_order);
  }
  return [...numbers].sort((a, b) => a - b);
};

export type FilteredGraph = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export const filterGraph = (graph: Graph, filters: GraphFilters): FilteredGraph => {
  const nodes = graph.nodes ?? [];
  const edges = graph.edges ?? [];

  const nodeOk = (node: GraphNode): boolean => {
    if (filters.tiers.length > 0 && !filters.tiers.includes(node.importance_tier)) { return false; }
    if (filters.bookFilter !== null && !(node.appears_in_books ?? []).includes(filters.bookFilter)) {
      return false;
    }
    return true;
  };
  const nodeOkById = new Map(nodes.map((node) => [node.id, nodeOk(node)]));

  const visibleEdges = edges.filter((edge) => {
    if (!nodeOkById.get(edge.source) || !nodeOkById.get(edge.target)) { return false; }
    if (filters.families.length > 0 && !filters.families.includes(edge.family)) { return false; }
    if (edge.confidence < filters.minConfidence) { return false; }
    if (filters.bookFilter !== null && !edgeBookOrders(edge).includes(filters.bookFilter)) {
      return false;
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
    (node) => nodeOkById.get(node.id) && (!narrowed || connected.has(node.id)),
  );

  return { nodes: visibleNodes, edges: visibleEdges };
};

import type { QueryRoute } from "@/lib/api";

/**
 * "answered from the character graph" — shown subtly under a completed
 * answer. It builds trust and it is free (frontend-1.md, S6.10).
 */
export const ROUTE_LABEL: Record<QueryRoute, string> = {
  character_lookup: "the character record",
  relationship_lookup: "the relationship graph",
  path: "a path traced through the graph",
  aggregation: "an exhaustive graph query",
  series_arc: "the relationship's arc across the series",
  narrative: "the text itself",
  ambiguous: "a clarifying question",
};

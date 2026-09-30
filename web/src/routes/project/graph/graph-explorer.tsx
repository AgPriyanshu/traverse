import { Box, Button, HStack, Heading, Stack, Text } from "@chakra-ui/react";
import { useCallback, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui";
import type { Book } from "@/lib/api";
import { useOntology, useProject, useProjectGraph } from "@/lib/api";
import { formatCount } from "@/lib/format";
import { sortedBooks } from "../project-lookup";
import { useProjectScope } from "../project-scope";
import { useReadingPositionContext } from "../reading-position-context";
import { buildNodeIndex, contextFor } from "./edge-context";
import { EvidencePanel } from "./evidence-panel";
import { GraphCanvas } from "./graph-canvas";
import { GraphFilterBar } from "./graph-filter-bar";
import { filterGraph, parseFilters, writeFilters } from "./graph-filters";
import type { GraphFilters } from "./graph-filters";
import { GraphLegend } from "./graph-legend";
import { GraphListView } from "./graph-list-view";

const EMPTY_BOOKS: Book[] = [];
const NARROW_QUERY = "(max-width: 47.99em)";

const defaultView = (): "graph" | "list" => {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return "graph";
  }
  return window.matchMedia(NARROW_QUERY).matches ? "list" : "graph";
};

/**
 * The series graph: one standing graph across every ingested book, sliced by
 * a client-side book filter (animated, S5.11) and hard-cut by the reading
 * position from the persistent slider in `<ProjectLayout>`
 * (server-side `limit_book_order`/`limit_chapter`, spoiler-safe, S8.6).
 */
export const GraphExplorer = () => {
  // Hooks.
  const { projectId, basePath, bookId, bookOrder } = useProjectScope();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  // Context.
  const { limitBookOrder, limitChapter } = useReadingPositionContext();

  // Apis.
  const project = useProject(projectId);
  const ontology = useOntology();
  const graph = useProjectGraph(projectId, {
    limit_book_order: limitBookOrder,
    limit_chapter: limitChapter ?? undefined,
  });

  // Variables.
  const books = useMemo(() => sortedBooks(project.data?.books ?? EMPTY_BOOKS), [project.data]);
  const view = searchParams.get("view") ?? defaultView();
  const selectedEdgeId = searchParams.get("edge");

  // useMemos.
  const urlFilters = useMemo(() => parseFilters(searchParams), [searchParams]);
  // A book's graph is pinned to that book, so its own filter is never shown or written to the URL.
  const filters = useMemo(
    () => (bookId === null ? urlFilters : { ...urlFilters, bookFilter: bookOrder }),
    [urlFilters, bookId, bookOrder],
  );
  const barFilters = useMemo(
    () => (bookId === null ? urlFilters : { ...urlFilters, bookFilter: null }),
    [urlFilters, bookId],
  );
  const filterBarBooks = useMemo(
    () => (bookId === null ? books : books.filter((book) => book.id === bookId)),
    [books, bookId],
  );
  const nodeIndex = useMemo(() => buildNodeIndex(graph.data), [graph.data]);
  const allNodes = useMemo(() => graph.data?.nodes ?? [], [graph.data]);
  const allEdges = useMemo(() => graph.data?.edges ?? [], [graph.data]);
  const filtered = useMemo(
    () => (graph.data ? filterGraph(graph.data, filters) : { nodes: [], edges: [] }),
    [graph.data, filters],
  );
  const visibleNodeIds = useMemo(() => new Set(filtered.nodes.map((node) => node.id)), [filtered.nodes]);
  const visibleEdgeIds = useMemo(() => new Set(filtered.edges.map((edge) => edge.id)), [filtered.edges]);
  const symmetric = useMemo(
    () =>
      new Set(
        (ontology.data?.predicates ?? [])
          .filter((predicate) => predicate.symmetric)
          .map((predicate) => predicate.predicate),
      ),
    [ontology.data],
  );
  const selected = useMemo(() => {
    const edge = allEdges.find((candidate) => candidate.id === selectedEdgeId);
    return edge ? contextFor(edge, nodeIndex) : null;
  }, [allEdges, selectedEdgeId, nodeIndex]);

  // Handlers.
  const updateParams = useCallback(
    (mutate: (next: URLSearchParams) => void) => {
      const next = new URLSearchParams(searchParams);
      mutate(next);
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const handleFilters = (next: GraphFilters) => {
    setSearchParams(writeFilters(searchParams, bookId === null ? next : { ...next, bookFilter: null }), { replace: true });
  };

  const handleSelectEdgeId = useCallback(
    (edgeId: string) => {
      updateParams((next) => { next.set("edge", edgeId); });
    },
    [updateParams],
  );

  const handleSelectNode = useCallback(
    (nodeId: string) => {
      void navigate(`${basePath}/characters/${nodeId}`);
    },
    [navigate, basePath],
  );

  const handleView = (next: "graph" | "list") => {
    updateParams((params) => { params.set("view", next); });
  };

  const handleClosePanel = () => {
    updateParams((next) => { next.delete("edge"); });
  };

  // Early returns.
  if (project.isPending || graph.isPending) {
    return <LoadingSkeleton variant="text" count={6} label="Loading the relationship graph" />;
  }
  if (project.error || graph.error) {
    return (
      <ErrorState
        error={(project.error ?? graph.error) as Error}
        onRetry={() => { void graph.refetch(); }}
      />
    );
  }
  if (allEdges.length === 0) {
    return (
      <EmptyState
        title="No relationships extracted yet"
        description="The relationship graph fills in once pass-2 relation extraction has run for at least one book."
      />
    );
  }

  return (
    <Stack gap="5">
      <HStack justify="space-between" align="flex-end" wrap="wrap" gap="3">
        <Stack gap="1">
          <Heading as="h2" textStyle="heading">
            Relationships
          </Heading>
          <Text textStyle="data" color="fg.muted" aria-live="polite">
            {formatCount(filtered.nodes.length, "character")} ·{" "}
            {formatCount(filtered.edges.length, "relationship")}
            {graph.data.truncated ? " · truncated by the server" : ""}
          </Text>
        </Stack>
        <HStack gap="1" role="group" aria-label="View">
          {(["graph", "list"] as const).map((option) => (
            <Button
              key={option}
              size="sm"
              variant="outline"
              aria-pressed={view === option}
              borderColor={view === option ? "accent.solid" : "border.control"}
              bg={view === option ? "accent.subtle" : "transparent"}
              color="fg"
              onClick={() => { handleView(option); }}
            >
              {option === "graph" ? "Graph view" : "List view"}
            </Button>
          ))}
        </HStack>
      </HStack>

      <GraphFilterBar filters={barFilters} books={filterBarBooks} onChange={handleFilters} />

      <GraphLegend />

      {view === "list" ? (
        <GraphListView
          nodes={filtered.nodes}
          edges={filtered.edges}
          basePath={basePath}
          firstInBookFilter={filters.bookFilter}
          onSelectEdge={(edge) => { handleSelectEdgeId(edge.id); }}
        />
      ) : (
        <Box>
          <GraphCanvas
            nodes={allNodes}
            edges={allEdges}
            visibleNodeIds={visibleNodeIds}
            visibleEdgeIds={visibleEdgeIds}
            symmetricPredicates={symmetric}
            selectedEdgeId={selectedEdgeId}
            firstInBookFilter={filters.bookFilter}
            onSelectEdge={handleSelectEdgeId}
            onSelectNode={handleSelectNode}
            ariaLabel="Character relationship graph. The list view has the same information as text."
          />
          <Text textStyle="small" color="fg.muted" marginBlockStart="2">
            Click a line for its evidence, a character for their page. The list view
            is the keyboard and screen-reader equivalent.
          </Text>
        </Box>
      )}

      <EvidencePanel target={selected} books={books} onClose={handleClosePanel} />
    </Stack>
  );
};

export default GraphExplorer;

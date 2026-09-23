import { Box, Button, HStack, Heading, Stack, Text } from "@chakra-ui/react";
import { useCallback, useMemo } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui";
import type { Chapter } from "@/lib/api";
import {
  useBook,
  useChapters,
  useOntology,
  useProjectGraph,
} from "@/lib/api";
import { formatCount } from "@/lib/format";
import { buildNodeIndex, contextFor } from "./edge-context";
import { EvidencePanel } from "./evidence-panel";
import { GraphCanvas } from "./graph-canvas";
import { GraphFilterBar } from "./graph-filter-bar";
import { filterGraph, parseFilters, writeFilters } from "./graph-filters";
import type { GraphFilters } from "./graph-filters";
import { GraphLegend } from "./graph-legend";
import { GraphListView } from "./graph-list-view";

const EMPTY_CHAPTERS: Chapter[] = [];
const NARROW_QUERY = "(max-width: 47.99em)";

const defaultView = (): "graph" | "list" => {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return "graph";
  }
  return window.matchMedia(NARROW_QUERY).matches ? "list" : "graph";
};

export const GraphExplorer = () => {
  // Hooks.
  const { bookId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  // Apis.
  const book = useBook(bookId);
  const chapters = useChapters(bookId);
  const ontology = useOntology();
  const graph = useProjectGraph(book.data?.project_id, { book_id: bookId });

  // Variables.
  const chapterList = chapters.data ?? EMPTY_CHAPTERS;
  const view = searchParams.get("view") ?? defaultView();
  const selectedEdgeId = searchParams.get("edge");
  const chapterCount = book.data?.chapter_count ?? 0;

  // useMemos.
  const filters = useMemo(() => parseFilters(searchParams), [searchParams]);
  const nodeIndex = useMemo(() => buildNodeIndex(graph.data), [graph.data]);
  const allNodes = useMemo(() => graph.data?.nodes ?? [], [graph.data]);
  const allEdges = useMemo(() => graph.data?.edges ?? [], [graph.data]);
  const filtered = useMemo(
    () => (graph.data ? filterGraph(graph.data, filters, chapterList) : { nodes: [], edges: [] }),
    [graph.data, filters, chapterList],
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
    setSearchParams(writeFilters(searchParams, next), { replace: true });
  };

  const handleSelectEdgeId = useCallback(
    (edgeId: string) => {
      updateParams((next) => { next.set("edge", edgeId); });
    },
    [updateParams],
  );

  const handleSelectNode = useCallback(
    (nodeId: string) => {
      void navigate(`/books/${bookId}/characters/${nodeId}`);
    },
    [navigate, bookId],
  );

  const handleView = (next: "graph" | "list") => {
    updateParams((params) => { params.set("view", next); });
  };

  const handleClosePanel = () => {
    updateParams((next) => { next.delete("edge"); });
  };

  // Early returns.
  if (book.isPending || graph.isPending) {
    return <LoadingSkeleton variant="text" count={6} label="Loading the relationship graph" />;
  }
  if (book.error || graph.error) {
    return (
      <ErrorState
        error={(book.error ?? graph.error) as Error}
        onRetry={() => { void graph.refetch(); }}
      />
    );
  }
  if (allEdges.length === 0) {
    return (
      <EmptyState
        title="No relationships extracted yet"
        description="The relationship graph fills in once pass-2 relation extraction has run for this book."
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

      <GraphFilterBar filters={filters} chapters={chapterList} onChange={handleFilters} />

      <GraphLegend />

      {view === "list" ? (
        <GraphListView
          nodes={filtered.nodes}
          edges={filtered.edges}
          chapters={chapterList}
          bookId={bookId}
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

      <EvidencePanel
        target={selected}
        bookId={bookId}
        bookTitle={book.data.title}
        chapterCount={chapterCount}
        onClose={handleClosePanel}
      />
    </Stack>
  );
};

export default GraphExplorer;

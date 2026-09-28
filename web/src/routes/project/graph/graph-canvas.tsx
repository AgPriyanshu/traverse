import { Box } from "@chakra-ui/react";
import cytoscape from "cytoscape";
import type { Core, ElementDefinition, StylesheetJson } from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useRef } from "react";
import { useColorMode } from "@/design-system/use-color-mode";
import type { GraphEdge, GraphNode, ImportanceTier } from "@/lib/api";
import { FAMILY_COLOR_VAR, FAMILY_DASH } from "./relation-style";

cytoscape.use(fcose);

const TIER_BASE_SIZE: Record<ImportanceTier, number> = {
  protagonist: 40,
  major: 30,
  minor: 21,
  mentioned: 14,
};

/** Every extra book a character has appeared in beyond the first widens the node — total appearances, not just the current slice's mention count (S5.11). */
const APPEARANCE_STEP = 4;
const MAX_APPEARANCE_BONUS = 24;

const nodeSize = (node: Pick<GraphNode, "importance_tier" | "appears_in_books">): number => {
  const extra = Math.max(0, (node.appears_in_books ?? []).length - 1);
  return TIER_BASE_SIZE[node.importance_tier] + Math.min(MAX_APPEARANCE_BONUS, extra * APPEARANCE_STEP);
};

const LABEL_FONT_SIZE = 12;
const FIT_PADDING = 40;
const FADE_MS = 220;
const FIT_MS = 320;

/** Resolves a CSS variable to a concrete colour, since canvas styles cannot read `var()`. */
const resolveColor = (value: string): string => {
  const probe = document.createElement("span");
  probe.style.color = value;
  document.body.appendChild(probe);
  const resolved = getComputedStyle(probe).color;
  probe.remove();
  return resolved;
};

const resolveFont = (): string => {
  const probe = document.createElement("span");
  probe.style.fontFamily = "var(--chakra-fonts-body)";
  document.body.appendChild(probe);
  const resolved = getComputedStyle(probe).fontFamily;
  probe.remove();
  return resolved || "sans-serif";
};

const edgeWidth = (count: number): number => {
  return 1 + Math.min(6, Math.log2(count + 1) * 1.1);
};

const prefersReducedMotion = (): boolean => {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
};

const buildStyle = (): StylesheetJson => {
  const fg = resolveColor("var(--chakra-colors-fg)");
  const surface = resolveColor("var(--chakra-colors-bg-surface)");
  const accent = resolveColor("var(--chakra-colors-accent-solid)");
  const font = resolveFont();

  const style: StylesheetJson = [
    {
      selector: "node",
      style: {
        width: "data(size)",
        height: "data(size)",
        "background-color": surface,
        "border-width": 2,
        "border-color": fg,
        label: "data(label)",
        color: fg,
        "font-family": font,
        "font-size": LABEL_FONT_SIZE,
        "text-valign": "bottom",
        "text-margin-y": 4,
        "text-wrap": "ellipsis",
        "text-max-width": "110px",
        "text-background-color": surface,
        "text-background-opacity": 0.85,
        "text-background-padding": "2px",
        "min-zoomed-font-size": LABEL_FONT_SIZE,
      },
    },
    {
      selector: 'node[tier = "protagonist"], node[tier = "major"]',
      style: { "min-zoomed-font-size": 0 },
    },
    {
      selector: 'node[tier = "protagonist"]',
      style: { "background-color": accent, "font-weight": 700 },
    },
    {
      selector: "node.first-in-book",
      style: {
        "border-width": 3,
        "border-style": "dashed",
        "border-color": accent,
      },
    },
    {
      selector: "edge",
      style: {
        width: "data(width)",
        "curve-style": "bezier",
        "line-color": "data(color)",
        "target-arrow-color": "data(color)",
        "line-style": "data(lineStyle)" as unknown as "solid",
        opacity: 0.85,
        "arrow-scale": 0.8,
      },
    },
    { selector: "edge[?hearsay]", style: { opacity: 0.55 } },
    { selector: "edge[?arrow]", style: { "target-arrow-shape": "triangle" } },
    {
      selector: "edge[dash]",
      style: { "line-dash-pattern": "data(dash)" as unknown as number[] },
    },
    {
      selector: ":selected",
      style: { "overlay-color": accent, "overlay-opacity": 0.2, "overlay-padding": 6 },
    },
    {
      selector: "node.picked",
      style: { "border-width": 4, "border-color": accent },
    },
    {
      selector: "edge.picked",
      style: { opacity: 1, "z-index": 10 },
    },
    { selector: ".faded", style: { opacity: 0.15 } },
    { selector: "node:active", style: { "overlay-opacity": 0.1 } },
  ];
  return style;
};

const familyColors = (): Map<string, string> => {
  const colors = new Map<string, string>();
  for (const [family, value] of Object.entries(FAMILY_COLOR_VAR)) {
    colors.set(family, resolveColor(value));
  }
  return colors;
};

const toElements = (
  nodes: readonly GraphNode[],
  edges: readonly GraphEdge[],
  symmetric: ReadonlySet<string>,
): ElementDefinition[] => {
  const elements: ElementDefinition[] = [];
  for (const node of nodes) {
    elements.push({
      group: "nodes",
      data: {
        id: node.id,
        label: node.canonical_name,
        tier: node.importance_tier,
        size: nodeSize(node),
        firstBookOrder: node.first_book_order ?? null,
      },
    });
  }
  for (const edge of edges) {
    const dash = FAMILY_DASH[edge.family];
    elements.push({
      group: "edges",
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        family: edge.family,
        width: edgeWidth(edge.evidence_count),
        arrow: !symmetric.has(edge.predicate),
        hearsay: edge.hearsay,
        lineStyle: dash.length === 0 ? "solid" : "dashed",
        dash: dash.length === 0 ? undefined : dash,
      },
    });
  }
  return elements;
};

export type GraphCanvasProps = {
  /** The full graph: layout is computed once over this, never over a filtered slice. */
  nodes: readonly GraphNode[];
  edges: readonly GraphEdge[];
  visibleNodeIds: ReadonlySet<string>;
  visibleEdgeIds: ReadonlySet<string>;
  symmetricPredicates: ReadonlySet<string>;
  selectedEdgeId: string | null;
  /** The active book slice's series_order, for the "first appears here" badge — `null` draws no badge. */
  firstInBookFilter?: number | null;
  onSelectEdge: (edgeId: string) => void;
  onSelectNode: (nodeId: string) => void;
  ariaLabel: string;
};

/**
 * Positions are computed once over the whole graph. A filter change hides and
 * reveals elements in place and animates the viewport, so the reader sees what
 * changed rather than a new, unrelated layout (S4.11) — the book filter uses
 * the same mechanism (S5.11): it is a slice of the standing graph, not a
 * fresh fetch, so the animation reads as "this is the same graph, narrowed"
 * rather than "here is a different graph."
 */
export const GraphCanvas = ({
  nodes,
  edges,
  visibleNodeIds,
  visibleEdgeIds,
  symmetricPredicates,
  selectedEdgeId,
  firstInBookFilter = null,
  onSelectEdge,
  onSelectNode,
  ariaLabel,
}: GraphCanvasProps) => {
  // Refs.
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const handlersRef = useRef({ onSelectEdge, onSelectNode });
  const firstVisibilityRef = useRef(true);
  // What `cyRef.current` currently reflects — kept current by both effects
  // below so a theme/symmetric rebuild always rebuilds from the latest data,
  // not whatever `nodes`/`edges` this component instance first mounted with.
  const graphRef = useRef<{ nodes: readonly GraphNode[]; edges: readonly GraphEdge[] }>({
    nodes,
    edges,
  });

  // Context.
  const { colorMode } = useColorMode();

  // useEffects.
  useEffect(() => {
    handlersRef.current = { onSelectEdge, onSelectNode };
  }, [onSelectEdge, onSelectNode]);

  // Builds a fresh cy instance and lays it out from scratch. Runs on mount
  // and on a theme/ontology change — deliberately not on every `nodes`/`edges`
  // change, so a reading-position re-fetch never resets positions the reader
  // already has a mental map of (see the incremental-update effect below).
  useEffect(() => {
    const container = containerRef.current;
    if (!container) { return undefined; }

    const { nodes: currentNodes, edges: currentEdges } = graphRef.current;

    const cy = cytoscape({
      container,
      elements: toElements(currentNodes, currentEdges, symmetricPredicates),
      style: buildStyle(),
      minZoom: 0.2,
      maxZoom: 3,
      textureOnViewport: true,
      hideEdgesOnViewport: currentEdges.length > 600,
      layout: { name: "preset" },
    });
    cyRef.current = cy;

    const colors = familyColors();
    cy.edges().forEach((edge) => {
      edge.data("color", colors.get(edge.data("family") as string));
    });

    cy.layout({
      name: "fcose",
      animate: false,
      randomize: true,
      quality: "default",
      nodeDimensionsIncludeLabels: true,
      idealEdgeLength: 110,
      nodeRepulsion: 9000,
      padding: FIT_PADDING,
    } as cytoscape.LayoutOptions).run();
    cy.fit(undefined, FIT_PADDING);

    cy.on("tap", "node", (event) => {
      handlersRef.current.onSelectNode(event.target.id() as string);
    });
    cy.on("tap", "edge", (event) => {
      handlersRef.current.onSelectEdge(event.target.id() as string);
    });
    cy.on("mouseover", "node", (event) => {
      const hood = event.target.closedNeighborhood();
      cy.elements().not(hood).addClass("faded");
    });
    cy.on("mouseout", "node", () => {
      cy.elements().removeClass("faded");
    });

    firstVisibilityRef.current = true;

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
    // Theme and the symmetric-predicate set are the only things that force a
    // full rebuild; a data change is handled incrementally below instead.
  }, [symmetricPredicates, colorMode]);

  // Updates the existing cy instance in place when `nodes`/`edges` change —
  // almost always the reading-position slider re-fetching a smaller (or, on
  // widening, larger) graph (S8.6). Elements the new fetch dropped fade out
  // and are removed from their *existing* positions rather than the whole
  // graph re-laying-out from scratch, so "the reader sees nodes and edges
  // leave" is a real transition, not a jump cut to an unrelated layout.
  useEffect(() => {
    const cy = cyRef.current;
    const previous = graphRef.current;
    if (!cy || (previous.nodes === nodes && previous.edges === edges)) {
      graphRef.current = { nodes, edges };
      return undefined;
    }

    const newNodeIds = new Set(nodes.map((node) => node.id));
    const newEdgeIds = new Set(edges.map((edge) => edge.id));
    const oldNodeIds = new Set(previous.nodes.map((node) => node.id));
    const oldEdgeIds = new Set(previous.edges.map((edge) => edge.id));

    const leaving = cy
      .elements()
      .filter((element) => (element.isNode() ? !newNodeIds.has(element.id()) : !newEdgeIds.has(element.id())));
    const enteringNodes = nodes.filter((node) => !oldNodeIds.has(node.id));
    const enteringEdges = edges.filter((edge) => !oldEdgeIds.has(edge.id));

    const duration = prefersReducedMotion() ? 0 : FADE_MS;

    const apply = () => {
      cy.batch(() => {
        leaving.remove();
        const colors = familyColors();
        const addedNodes = cy.add(toElements(enteringNodes, [], symmetricPredicates));
        const addedEdges = cy.add(toElements([], enteringEdges, symmetricPredicates));
        addedEdges.forEach((edge) => { edge.data("color", colors.get(edge.data("family") as string)); });
        if (duration > 0) {
          addedNodes.style({ opacity: 0 });
          addedNodes.animate({ style: { opacity: 1 } }, { duration });
          // Target opacity matches the stylesheet's own `edge`/`edge[?hearsay]`
          // rules per element — an inline style set via `.animate` would
          // otherwise pin every future frame's opacity, overriding hearsay
          // dimming permanently for a freshly-added edge.
          addedEdges.forEach((edge) => {
            const targetOpacity = edge.data("hearsay") ? 0.55 : 0.85;
            edge.style({ opacity: 0 });
            edge.animate({ style: { opacity: targetOpacity } }, { duration });
          });
        }
      });
      if (enteringNodes.length > 0) {
        // New characters have no position yet — relaying out only unlocked
        // (new) elements keeps everything already on screen where it was.
        cy.layout({
          name: "fcose",
          animate: false,
          randomize: false,
          quality: "default",
          nodeDimensionsIncludeLabels: true,
          idealEdgeLength: 110,
          nodeRepulsion: 9000,
          padding: FIT_PADDING,
        } as cytoscape.LayoutOptions).run();
      }
      const remaining = cy.elements();
      if (remaining.length > 0) {
        if (duration > 0) {
          cy.animate({ fit: { eles: remaining, padding: FIT_PADDING } }, { duration: FIT_MS });
        } else {
          cy.fit(remaining, FIT_PADDING);
        }
      }
      graphRef.current = { nodes, edges };
    };

    if (leaving.length > 0 && duration > 0) {
      leaving.animate({ style: { opacity: 0 } }, { duration });
      const timeoutId = window.setTimeout(apply, duration);
      return () => { window.clearTimeout(timeoutId); };
    }
    apply();
    return undefined;
  }, [nodes, edges, symmetricPredicates]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) { return; }
    const duration = prefersReducedMotion() || firstVisibilityRef.current ? 0 : FADE_MS;
    const fit = prefersReducedMotion() || firstVisibilityRef.current ? 0 : FIT_MS;
    firstVisibilityRef.current = false;

    // An element the data-diff effect above is mid-fade-removing for (a real
    // reading-position re-fetch, not this client-side filter) is skipped here
    // entirely — `display: none` is instant and would cut its fade-out short.
    const currentNodeIds = new Set(nodes.map((node) => node.id));
    const currentEdgeIds = new Set(edges.map((edge) => edge.id));

    cy.batch(() => {
      cy.nodes().forEach((node) => {
        if (!currentNodeIds.has(node.id())) { return; }
        const shouldShow = visibleNodeIds.has(node.id());
        if (shouldShow && node.style("display") === "none") {
          node.style({ display: "element", opacity: 0 });
          if (duration > 0) {
            node.animate({ style: { opacity: 1 } }, { duration });
          } else {
            node.style({ opacity: 1 });
          }
        } else if (!shouldShow) {
          node.style({ display: "none" });
        }
      });
      cy.edges().forEach((edge) => {
        if (!currentEdgeIds.has(edge.id())) { return; }
        const shouldShow = visibleEdgeIds.has(edge.id()) &&
          visibleNodeIds.has(edge.source().id()) &&
          visibleNodeIds.has(edge.target().id());
        edge.style({ display: shouldShow ? "element" : "none" });
      });
    });

    const shown = cy.elements().filter((element) => element.style("display") !== "none");
    if (shown.length > 0) {
      if (fit > 0) {
        cy.animate({ fit: { eles: shown, padding: FIT_PADDING } }, { duration: fit });
      } else {
        cy.fit(shown, FIT_PADDING);
      }
    }
  }, [visibleNodeIds, visibleEdgeIds, nodes, edges, colorMode]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) { return; }
    cy.elements().removeClass("picked");
    if (selectedEdgeId) {
      const edge = cy.getElementById(selectedEdgeId);
      edge.addClass("picked");
      edge.connectedNodes().addClass("picked");
    }
  }, [selectedEdgeId, nodes, edges, colorMode]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) { return; }
    cy.nodes().forEach((node) => {
      const matches =
        firstInBookFilter !== null && node.data("firstBookOrder") === firstInBookFilter;
      node.toggleClass("first-in-book", matches);
    });
  }, [firstInBookFilter, nodes, edges, colorMode]);

  return (
    <Box
      ref={containerRef}
      role="img"
      aria-label={ariaLabel}
      height={{ base: "70vh", md: "72vh" }}
      minHeight="80"
      borderWidth="1px"
      borderColor="border"
      borderRadius="lg"
      bg="bg.surface"
    />
  );
};

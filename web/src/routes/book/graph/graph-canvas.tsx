import { Box } from "@chakra-ui/react";
import cytoscape from "cytoscape";
import type { Core, ElementDefinition, StylesheetJson } from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useRef } from "react";
import { useColorMode } from "@/design-system/use-color-mode";
import type { GraphEdge, GraphNode, ImportanceTier } from "@/lib/api";
import { FAMILY_COLOR_VAR, FAMILY_DASH } from "./relation-style";

cytoscape.use(fcose);

const NODE_SIZE: Record<ImportanceTier, number> = {
  protagonist: 46,
  major: 34,
  minor: 24,
  mentioned: 16,
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
        size: NODE_SIZE[node.importance_tier],
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
  onSelectEdge: (edgeId: string) => void;
  onSelectNode: (nodeId: string) => void;
  ariaLabel: string;
};

/**
 * Positions are computed once over the whole graph. A filter change hides and
 * reveals elements in place and animates the viewport, so the reader sees what
 * changed rather than a new, unrelated layout (S4.11).
 */
export const GraphCanvas = ({
  nodes,
  edges,
  visibleNodeIds,
  visibleEdgeIds,
  symmetricPredicates,
  selectedEdgeId,
  onSelectEdge,
  onSelectNode,
  ariaLabel,
}: GraphCanvasProps) => {
  // Refs.
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const handlersRef = useRef({ onSelectEdge, onSelectNode });
  const firstVisibilityRef = useRef(true);

  // Context.
  const { colorMode } = useColorMode();

  // useEffects.
  useEffect(() => {
    handlersRef.current = { onSelectEdge, onSelectNode };
  }, [onSelectEdge, onSelectNode]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) { return undefined; }

    const cy = cytoscape({
      container,
      elements: toElements(nodes, edges, symmetricPredicates),
      style: buildStyle(),
      minZoom: 0.2,
      maxZoom: 3,
      textureOnViewport: true,
      hideEdgesOnViewport: edges.length > 600,
      layout: { name: "preset" },
    });
    cyRef.current = cy;

    const colors = new Map<string, string>();
    for (const [family, value] of Object.entries(FAMILY_COLOR_VAR)) {
      colors.set(family, resolveColor(value));
    }
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
    // The layout is deliberately built once per graph or theme, never per filter change.
  }, [nodes, edges, symmetricPredicates, colorMode]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) { return; }
    const duration = prefersReducedMotion() || firstVisibilityRef.current ? 0 : FADE_MS;
    const fit = prefersReducedMotion() || firstVisibilityRef.current ? 0 : FIT_MS;
    firstVisibilityRef.current = false;

    cy.batch(() => {
      cy.nodes().forEach((node) => {
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

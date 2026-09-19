import { Box, Button, HStack, IconButton, Image, Input, Stack, Text } from "@chakra-ui/react";
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronLeftIcon, ChevronRightIcon } from "@/components/ui/icons";
import { ErrorState, LoadingSkeleton } from "@/components/ui";
import { pageRenderQueryOptions, usePageRender } from "@/lib/api";
import { formatCount } from "@/lib/format";

export type HighlightKind = "citation" | "search";

/**
 * The PDF-user-space coordinate system `SpanBox` uses (top-left origin,
 * unscaled points) — `PageRenderOut.width`/`.height` are assumed to share it
 * (flagged for be1 to confirm in `plans/sprint-2/HANDOFF.md`, since
 * `render_page` isn't implemented yet). A citation link builds one of these
 * from a `SpanBox` it already has; nothing here ever converts pixels back to
 * points, which is exactly why that assumption has to hold.
 */
export type Highlight = {
  page: number;
  x: number;
  y: number;
  w: number;
  h: number;
  kind?: HighlightKind;
};

export type PageViewerProps = {
  bookId: string;
  page: number;
  /** Omitted while the book itself is still loading — navigation just won't clamp yet. */
  pageCount?: number | null;
  highlights?: Highlight[];
  onNavigate?: (page: number) => void;
};

type ZoomMode = "fit-width" | "fit-page" | "100" | "200";

const ZOOM_MODES: { mode: ZoomMode; label: string }[] = [
  { mode: "fit-width", label: "Fit width" },
  { mode: "fit-page", label: "Fit page" },
  { mode: "100", label: "100%" },
  { mode: "200", label: "200%" },
];

// The chrome above the image (app header, book tabs, this toolbar) is not
// measured live — an approximation is enough for "fit page" to mean
// "roughly the whole page, no scrolling", not a pixel-exact budget.
const FIT_PAGE_CHROME_ALLOWANCE = "230px";

const HIGHLIGHT_COLOR: Record<HighlightKind, string> = {
  citation: "accent.solid",
  search: "status.ok",
};

export const PageViewer = ({
  bookId,
  page,
  pageCount,
  highlights = [],
  onNavigate,
}: PageViewerProps) => {
  // States.
  const [zoom, setZoom] = useState<ZoomMode>("fit-width");
  const [naturalSize, setNaturalSize] = useState<{
    width: number;
    height: number;
  } | null>(null);
  const [jumpValue, setJumpValue] = useState(String(page));
  // Not an effect: React's own pattern for resetting state when a prop
  // changes — a render-phase setState, processed before the browser paints,
  // rather than a post-commit effect that would flash the stale natural size
  // or jump-field value for a frame.
  const [trackedPage, setTrackedPage] = useState(page);
  if (page !== trackedPage) {
    setTrackedPage(page);
    setNaturalSize(null);
    setJumpValue(String(page));
  }

  // Refs.
  const jumpInputRef = useRef<HTMLInputElement>(null);

  // Hooks.
  const queryClient = useQueryClient();

  // Apis.
  const render = usePageRender(bookId, page);

  // Variables.
  const pageData = render.data;
  const canGoPrev = page > 1;
  const canGoNext = pageCount ? page < pageCount : true;
  const pageHighlights = highlights.filter((highlight) => highlight.page === page);
  const aspectRatio = pageData ? `${pageData.width} / ${pageData.height}` : undefined;

  // useEffects.
  useEffect(() => {
    if (canGoPrev) {
      void queryClient.prefetchQuery(pageRenderQueryOptions(bookId, page - 1));
    }
    if (canGoNext) {
      void queryClient.prefetchQuery(pageRenderQueryOptions(bookId, page + 1));
    }
  }, [bookId, page, canGoPrev, canGoNext, queryClient]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      const isTyping =
        target instanceof HTMLElement &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA");
      if (isTyping || event.metaKey || event.ctrlKey || event.altKey) { return; }

      if (event.key === "ArrowLeft" && canGoPrev) {
        event.preventDefault();
        onNavigate?.(page - 1);
      }
      if (event.key === "ArrowRight" && canGoNext) {
        event.preventDefault();
        onNavigate?.(page + 1);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => { window.removeEventListener("keydown", handleKeyDown); };
  }, [canGoPrev, canGoNext, page, onNavigate]);

  // Handlers.
  const handleJumpSubmit = () => {
    const parsed = Number.parseInt(jumpValue, 10);
    if (Number.isNaN(parsed) || parsed < 1) {
      setJumpValue(String(page));
      return;
    }
    const clamped = pageCount ? Math.min(parsed, pageCount) : parsed;
    if (clamped !== page) {
      onNavigate?.(clamped);
    } else {
      setJumpValue(String(page));
    }
  };

  // The image's own box IS the highlight layer's positioning context in
  // every mode: fit-width is block + width 100% (the natural analogue of
  // "the panel's width"); the rest shrink-wrap to the image's own computed
  // size, so there is never letterboxed empty space around it for a
  // percentage-based highlight to land in.
  const imageBoxStyle = (() => {
    if (zoom === "fit-width") {
      return { display: "block" as const, width: "100%", aspectRatio };
    }
    if (zoom === "fit-page") {
      return {
        display: "inline-block" as const,
        width: "auto",
        height: "auto",
        maxWidth: "100%",
        maxHeight: `calc(100dvh - ${FIT_PAGE_CHROME_ALLOWANCE})`,
        aspectRatio,
      };
    }
    const scale = zoom === "200" ? 2 : 1;
    if (naturalSize) {
      return {
        display: "inline-block" as const,
        width: `${naturalSize.width * scale}px`,
        height: `${naturalSize.height * scale}px`,
      };
    }
    // Native pixel size is unknown before the image's first load — fall back
    // to fit-width rather than a 0×0 box.
    return { display: "block" as const, width: "100%", aspectRatio };
  })();

  return (
    <Stack gap="4">
      <HStack
        justify="space-between"
        wrap="wrap"
        gap="3"
        borderBottomWidth="1px"
        borderColor="border"
        paddingBlockEnd="3"
      >
        <HStack gap="2">
          <IconButton
            aria-label="Previous page"
            title="Previous page"
            size="sm"
            variant="outline"
            borderColor="border.control"
            color="fg"
            borderRadius="md"
            disabled={!canGoPrev}
            onClick={() => onNavigate?.(page - 1)}
          >
            <ChevronLeftIcon />
          </IconButton>

          <form
            onSubmit={(event) => {
              event.preventDefault();
              handleJumpSubmit();
            }}
          >
            <HStack gap="2">
              <Text asChild textStyle="data" color="fg.subtle">
                <label htmlFor="page-jump">Page</label>
              </Text>
              <Input
                ref={jumpInputRef}
                id="page-jump"
                type="number"
                inputMode="numeric"
                min={1}
                max={pageCount ?? undefined}
                size="sm"
                width="16"
                textAlign="center"
                borderColor="border.control"
                borderRadius="md"
                value={jumpValue}
                onChange={(event) => { setJumpValue(event.target.value); }}
                onBlur={handleJumpSubmit}
              />
              {pageCount ? (
                <Text textStyle="data" color="fg.subtle">
                  of {pageCount}
                </Text>
              ) : null}
            </HStack>
          </form>

          <IconButton
            aria-label="Next page"
            title="Next page"
            size="sm"
            variant="outline"
            borderColor="border.control"
            color="fg"
            borderRadius="md"
            disabled={!canGoNext}
            onClick={() => onNavigate?.(page + 1)}
          >
            <ChevronRightIcon />
          </IconButton>
        </HStack>

        <HStack gap="1" role="group" aria-label="Zoom">
          {ZOOM_MODES.map(({ mode, label }) => (
            <Button
              key={mode}
              size="sm"
              variant={zoom === mode ? "solid" : "outline"}
              bg={zoom === mode ? "accent.solid" : undefined}
              color={zoom === mode ? "accent.contrast" : "fg"}
              borderColor="border.control"
              borderRadius="md"
              aria-pressed={zoom === mode}
              onClick={() => { setZoom(mode); }}
            >
              {label}
            </Button>
          ))}
        </HStack>
      </HStack>

      {render.isPending ? (
        <LoadingSkeleton variant="rows" count={1} label="Loading page" />
      ) : null}

      {render.error ? (
        <ErrorState error={render.error} onRetry={() => void render.refetch()} />
      ) : null}

      {pageData ? (
        <Box
          overflow="auto"
          borderWidth="1px"
          borderColor="border"
          borderRadius="lg"
          bg="bg.sunken"
          padding="4"
        >
          <Box position="relative" style={imageBoxStyle}>
            <Image
              src={pageData.image_url}
              alt={`Page ${page}`}
              display="block"
              width="100%"
              height="100%"
              onLoad={(event) => {
                const img = event.currentTarget;
                setNaturalSize({
                  width: img.naturalWidth,
                  height: img.naturalHeight,
                });
              }}
            />

            {pageHighlights.map((highlight, index) => (
              <Box
                key={`${highlight.x}-${highlight.y}-${index}`}
                data-highlight-kind={highlight.kind ?? "citation"}
                position="absolute"
                left={`${(highlight.x / pageData.width) * 100}%`}
                top={`${(highlight.y / pageData.height) * 100}%`}
                width={`${(highlight.w / pageData.width) * 100}%`}
                height={`${(highlight.h / pageData.height) * 100}%`}
                borderWidth="2px"
                borderColor={HIGHLIGHT_COLOR[highlight.kind ?? "citation"]}
                bg={HIGHLIGHT_COLOR[highlight.kind ?? "citation"]}
                opacity="0.28"
                borderRadius="sm"
                pointerEvents="none"
                aria-hidden="true"
              />
            ))}
          </Box>
        </Box>
      ) : null}

      <Text textStyle="data" color="fg.subtle">
        {formatCount(pageData?.spans?.length, "text span")}
      </Text>
    </Stack>
  );
};

export default PageViewer;

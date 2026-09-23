import { Box } from "@chakra-ui/react";
import type { KeyboardEvent } from "react";

export type SparkPoint = {
  /** The `mentions_per_chapter` dict key — a chapter number as a string, or an unbucketed sentinel. */
  key: string;
  /** What a reader sees: "Chapter 3", not "3". */
  label: string;
  value: number;
};

export type SparklineBarsProps = {
  data: SparkPoint[];
  width: number;
  height: number;
  ariaLabel: string;
  /** Non-interactive rows (the roster list) skip hit targets, focus and the selected style entirely. */
  interactive?: boolean;
  selectedKey?: string | null;
  onSelect?: (key: string | null) => void;
  /** Fills its container's width at a fixed height — the detail page's timeline, unlike the roster row's fixed-size mini chart. */
  responsive?: boolean;
};

const GAP_RATIO = 0.18;
const MIN_BAR_HEIGHT = 2;

/**
 * A single-hue magnitude chart — one series needs no legend (dataviz skill).
 * Interactive bars are real hit targets (rect + role="button" + keyboard),
 * not a decorative SVG with a click handler bolted on; the fill alone never
 * carries the selected state, since colour is never the only channel — the
 * selected bar also gets a visible ring and `aria-pressed`.
 */
export const SparklineBars = ({
  data,
  width,
  height,
  ariaLabel,
  interactive = false,
  selectedKey = null,
  onSelect,
  responsive = false,
}: SparklineBarsProps) => {
  if (data.length === 0) {
    return (
      <Box
        width={`${width}px`}
        height={`${height}px`}
        bg="bg.sunken"
        borderRadius="sm"
        role="img"
        aria-label={`${ariaLabel} — not available yet`}
      />
    );
  }

  const max = Math.max(1, ...data.map((point) => point.value));
  const slot = width / data.length;
  const barWidth = Math.max(1, slot * (1 - GAP_RATIO));
  const radius = Math.min(2, barWidth / 3);

  const handleKeyDown = (event: KeyboardEvent<SVGRectElement>, key: string) => {
    if (event.key !== "Enter" && event.key !== " ") { return; }
    event.preventDefault();
    onSelect?.(selectedKey === key ? null : key);
  };

  return (
    <svg
      width={responsive ? "100%" : width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role={interactive ? "group" : "img"}
      aria-label={interactive ? undefined : ariaLabel}
    >
      {data.map((point, index) => {
        const barHeight = Math.max(
          MIN_BAR_HEIGHT,
          (point.value / max) * height,
        );
        const x = index * slot + (slot - barWidth) / 2;
        const y = height - barHeight;
        const isSelected = interactive && selectedKey === point.key;

        return (
          <rect
            key={point.key}
            x={x}
            y={y}
            width={barWidth}
            height={barHeight}
            rx={radius}
            fill="var(--chakra-colors-accent-solid)"
            opacity={
              !interactive || selectedKey === null || isSelected ? 1 : 0.45
            }
            stroke={isSelected ? "var(--chakra-colors-fg)" : "none"}
            strokeWidth={isSelected ? 1.5 : 0}
            role={interactive ? "button" : undefined}
            tabIndex={interactive ? 0 : undefined}
            aria-pressed={interactive ? isSelected : undefined}
            aria-label={
              interactive
                ? `${point.label} — ${point.value.toLocaleString()} mentions`
                : undefined
            }
            cursor={interactive ? "pointer" : undefined}
            onClick={
              interactive
                ? () => { onSelect?.(selectedKey === point.key ? null : point.key); }
                : undefined
            }
            onKeyDown={
              interactive ? (event) => { handleKeyDown(event, point.key); } : undefined
            }
          >
            {interactive ? (
              <title>{`${point.label}: ${point.value.toLocaleString()} mentions`}</title>
            ) : null}
          </rect>
        );
      })}
      <line
        x1={0}
        y1={height}
        x2={width}
        y2={height}
        stroke="var(--chakra-colors-border)"
        strokeWidth={1}
      />
    </svg>
  );
};

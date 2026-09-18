/**
 * The frozen design tokens (design/DESIGN.md §3). Orchestrator-owned — a
 * missing value here is a DCR (BRANCH.md §8), never a local addition.
 *
 * Every colour is measured to clear 4.5:1 wherever it is actually used; see
 * the per-token notes below for which ground each was checked against.
 */
export const palette = {
  paper: { light: "#FAF7F2", dark: "#1C1815" },
  surface: { light: "#FFFDFA", dark: "#24201C" },
  sunken: { light: "#F2EDE4", dark: "#161311" },
  line: { light: "#E2DACD", dark: "#3A342E" },
  ink: { light: "#2B2622", dark: "#EDE6DC" },
  ink2: { light: "#6B6157", dark: "#B3A899" },
  ink3: { light: "#756A5C", dark: "#9C9183" },
  accent: { light: "#A8502A", dark: "#D98357" },
  accentSoft: { light: "#F4E7DF", dark: "#33251D" },
  ok: { light: "#3F6D45", dark: "#7FB98A" },
  warn: { light: "#8A5A12", dark: "#D2A44E" },
  err: { light: "#9E3B30", dark: "#E08A7E" },
  kinship: { light: "#2C6E6A", dark: "#63B5AE" },
  romantic: { light: "#A6385C", dark: "#E08098" },
  // DCR-2: the original #8A6A12 measured 4.34:1 on `sunken` — below the 4.5
  // floor, and the graph legend + relationship list sit on sunken wells.
  // Darkened to clear 4.92:1 there (5.37 on paper, 5.66 on surface).
  social: { light: "#7F6210", dark: "#C9A23C" },
  adversarial: { light: "#5D4A96", dark: "#A493DB" },
} as const;

/**
 * Shadow colour and alpha (DCR-3 — §3 specified geometry only). The `ink` hue
 * at low alpha, so shadows read as warm rather than a generic grey halo.
 */
export const shadow = {
  card: {
    light:
      "0 2px 3px -1px rgba(43, 38, 34, 0.09), 0 7px 14px -10px rgba(43, 38, 34, 0.22)",
    dark: "0 2px 3px -1px rgba(0, 0, 0, 0.30), 0 7px 14px -10px rgba(0, 0, 0, 0.55)",
  },
  raised: {
    light:
      "0 2px 3px -1px rgba(43, 38, 34, 0.14), 0 7px 14px -10px rgba(43, 38, 34, 0.34)",
    dark: "0 2px 3px -1px rgba(0, 0, 0, 0.40), 0 7px 14px -10px rgba(0, 0, 0, 0.65)",
  },
} as const;

export const type = {
  literata: '"Literata", "Iowan Old Style", Georgia, "Times New Roman", serif',
  plexSans: '"IBM Plex Sans", system-ui, "Segoe UI", Roboto, sans-serif',
  plexMono: '"IBM Plex Mono", ui-monospace, "SF Mono", Consolas, monospace',
} as const;

export const space = { unit: 4 } as const;

export const radius = {
  sm: "3px",
  md: "7px",
  lg: "10px",
  full: "999px",
} as const;

export const motion = { fast: "120ms", base: "200ms", slow: "320ms" } as const;

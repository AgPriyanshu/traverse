import { createSystem, defaultConfig, defineConfig } from "@chakra-ui/react";

// Transcribed verbatim from design/DESIGN.md §3 pending DCR-1, which asks the
// orchestrator to export `design-system/tokens.ts`. When that file lands this
// block becomes `import { palette } from "./tokens"` and nothing else changes.
const palette = {
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
  social: { light: "#8A6A12", dark: "#C9A23C" },
  adversarial: { light: "#5D4A96", dark: "#A493DB" },
} as const;

const dual = (name: keyof typeof palette) => {
  return { value: { base: palette[name].light, _dark: palette[name].dark } };
};

const literata = '"Literata", "Iowan Old Style", Georgia, "Times New Roman", serif';
const plexSans = '"IBM Plex Sans", system-ui, "Segoe UI", Roboto, sans-serif';
const plexMono = '"IBM Plex Mono", ui-monospace, "SF Mono", Consolas, monospace';

const config = defineConfig({
  globalCss: {
    ":root": {
      // Themes browser-owned surfaces rather than leaving them to the UA.
      colorScheme: "light dark",
      accentColor: "var(--chakra-colors-accent-solid)",
      caretColor: "var(--chakra-colors-accent-solid)",
      scrollbarColor:
        "var(--chakra-colors-border) var(--chakra-colors-bg-sunken)",
    },
    "html, body": {
      margin: 0,
      bg: "bg",
      color: "fg",
      fontFamily: "body",
      fontSize: "body",
      lineHeight: "1.55",
      fontSynthesis: "none",
      textRendering: "optimizeLegibility",
      fontSmooth: "antialiased",
    },
    body: {
      minHeight: "100dvh",
      overflowX: "hidden",
    },
    "*::selection": {
      bg: "accent.subtle",
      color: "fg",
    },
    "*:focus-visible": {
      outline: "2px solid",
      outlineColor: "accent.focusRing",
      outlineOffset: "2px",
      borderRadius: "sm",
    },
    a: {
      textUnderlineOffset: "0.18em",
      textDecorationThickness: "from-font",
    },
    "h1, h2, h3, h4": {
      fontFamily: "heading",
      color: "fg",
      fontWeight: "500",
      lineHeight: "1.25",
      textWrap: "balance",
    },
    // Respecting this is an accessibility requirement, not a preference.
    "*, *::before, *::after": {
      _motionReduce: {
        animationDuration: "0.01ms !important",
        animationIterationCount: "1 !important",
        transitionDuration: "0.01ms !important",
        scrollBehavior: "auto !important",
      },
    },
  },
  theme: {
    tokens: {
      fonts: {
        body: { value: plexSans },
        heading: { value: literata },
        serif: { value: literata },
        mono: { value: plexMono },
      },
      fontSizes: {
        display: { value: "30px" },
        heading: { value: "20px" },
        subheading: { value: "17px" },
        quote: { value: "16.5px" },
        body: { value: "14.5px" },
        small: { value: "12.5px" },
        data: { value: "12.5px" },
        micro: { value: "12px" },
      },
      radii: {
        sm: { value: "3px" },
        md: { value: "7px" },
        lg: { value: "10px" },
        full: { value: "999px" },
      },
      durations: {
        fast: { value: "120ms" },
        base: { value: "200ms" },
        slow: { value: "320ms" },
      },
      shadows: {
        // Offset plus a tight blur. A 1px border plus a wide soft halo is the
        // tell to avoid (DESIGN.md §3).
        card: {
          value:
            "0 2px 3px -1px rgba(43, 38, 34, 0.09), 0 7px 14px -10px rgba(43, 38, 34, 0.22)",
        },
        raised: {
          value:
            "0 2px 3px -1px rgba(43, 38, 34, 0.14), 0 7px 14px -10px rgba(43, 38, 34, 0.34)",
        },
      },
      sizes: {
        // A reading tool earns a measure, not a full-bleed dashboard grid.
        measure: { value: "68ch" },
        shell: { value: "1180px" },
        sidenav: { value: "208px" },
      },
    },
    semanticTokens: {
      colors: {
        bg: {
          DEFAULT: dual("paper"),
          surface: dual("surface"),
          sunken: dual("sunken"),
          panel: dual("surface"),
        },
        fg: {
          DEFAULT: dual("ink"),
          muted: dual("ink2"),
          subtle: dual("ink3"),
          inverted: {
            value: { base: palette.paper.dark, _dark: palette.paper.light },
          },
        },
        border: {
          DEFAULT: dual("line"),
          // `line` is 1.3:1 and decorative. Anything that is the boundary of a
          // control uses this instead, to clear WCAG 1.4.11 at 3:1.
          control: dual("ink3"),
        },
        accent: {
          solid: dual("accent"),
          fg: dual("accent"),
          muted: dual("accentSoft"),
          subtle: dual("accentSoft"),
          emphasized: dual("accent"),
          focusRing: dual("accent"),
          contrast: {
            value: { base: palette.paper.light, _dark: palette.paper.dark },
          },
        },
        status: {
          ok: dual("ok"),
          warn: dual("warn"),
          err: dual("err"),
          idle: dual("ink3"),
        },
        relation: {
          kinship: dual("kinship"),
          romantic: dual("romantic"),
          social: dual("social"),
          adversarial: dual("adversarial"),
        },
      },
      radii: {
        l1: { value: "{radii.sm}" },
        l2: { value: "{radii.md}" },
        l3: { value: "{radii.lg}" },
      },
    },
    textStyles: {
      display: {
        value: {
          fontFamily: literata,
          fontSize: "30px",
          fontWeight: "500",
          lineHeight: "1.2",
          letterSpacing: "-0.01em",
        },
      },
      heading: {
        value: {
          fontFamily: literata,
          fontSize: "20px",
          fontWeight: "500",
          lineHeight: "1.3",
        },
      },
      subheading: {
        value: {
          fontFamily: literata,
          fontSize: "17px",
          fontWeight: "500",
          lineHeight: "1.35",
        },
      },
      quote: {
        value: {
          fontFamily: literata,
          fontSize: "16.5px",
          fontStyle: "italic",
          lineHeight: "1.55",
        },
      },
      body: {
        value: { fontFamily: plexSans, fontSize: "14.5px", lineHeight: "1.55" },
      },
      small: {
        value: { fontFamily: plexSans, fontSize: "12.5px", lineHeight: "1.5" },
      },
      data: {
        value: {
          fontFamily: plexMono,
          fontSize: "12.5px",
          lineHeight: "1.5",
          fontVariantNumeric: "tabular-nums oldstyle-nums",
          fontFeatureSettings: '"tnum" 1, "onum" 1',
        },
      },
    },
  },
});

export const system = createSystem(defaultConfig, config);

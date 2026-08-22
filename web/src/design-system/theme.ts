import { createSystem, defaultConfig, defineConfig } from "@chakra-ui/react";

const config = defineConfig({
  globalCss: {
    "html, body": {
      margin: 0,
      color: "fg",
      bg: "bg",
      fontFamily: "body",
      fontSize: "18px",
      lineHeight: "145%",
      letterSpacing: "0.18px",
      fontSynthesis: "none",
      textRendering: "optimizeLegibility",
      fontSmooth: "antialiased",
      "@media (max-width: 1024px)": {
        fontSize: "16px",
      },
    },
  },
  theme: {
    tokens: {
      colors: {
        accent: {
          solid: { value: "#aa3bff" },
          subtle: { value: "rgba(170, 59, 255, 0.1)" },
          muted: { value: "rgba(170, 59, 255, 0.5)" },
        },
        surface: {
          code: { value: "#f4f3ec" },
          social: { value: "rgba(244, 243, 236, 0.5)" },
        },
      },
      fonts: {
        body: { value: 'system-ui, "Segoe UI", Roboto, sans-serif' },
        heading: { value: 'system-ui, "Segoe UI", Roboto, sans-serif' },
        mono: { value: "ui-monospace, Consolas, monospace" },
      },
      shadows: {
        card: {
          value:
            "rgba(0, 0, 0, 0.1) 0 10px 15px -3px, rgba(0, 0, 0, 0.05) 0 4px 6px -2px",
        },
      },
    },
    semanticTokens: {
      colors: {
        bg: {
          DEFAULT: { value: { base: "#fff", _dark: "#08060d" } },
        },
        fg: {
          DEFAULT: { value: { base: "#6b6375", _dark: "#e5e4e7" } },
          heading: { value: { base: "#08060d", _dark: "#fff" } },
        },
        border: {
          DEFAULT: { value: { base: "#e5e4e7", _dark: "#2a2830" } },
        },
      },
    },
  },
});

export const system = createSystem(defaultConfig, config);

import { describe, expect, it } from "vitest";
import { palette } from "@/design-system/tokens";

const luminance = (hex: string): number => {
  const value = hex.replace("#", "");
  const channel = (offset: number) => {
    const raw = Number.parseInt(value.slice(offset, offset + 2), 16) / 255;
    return raw <= 0.03928 ? raw / 12.92 : ((raw + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(2) + 0.0722 * channel(4);
};

const contrast = (a: string, b: string): number => {
  const [lighter, darker] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return ((lighter as number) + 0.05) / ((darker as number) + 0.05);
};

const GROUNDS = ["paper", "surface", "sunken"] as const;
const INKS = [
  "ink",
  "ink2",
  "ink3",
  "accent",
  "ok",
  "warn",
  "err",
  "kinship",
  "romantic",
  "social",
  "adversarial",
] as const;
const THEMES = ["light", "dark"] as const;

/**
 * NFR-a11y is an acceptance criterion on this sprint, not a Sprint 9 sweep, so
 * the palette is checked rather than eyeballed. Relation colours are included
 * now that Sprint 4 renders them (DCR-2 fixed light `social` on `sunken`).
 */
describe("the palette clears 4.5:1 on every ground it is used on", () => {
  for (const theme of THEMES) {
    for (const ground of GROUNDS) {
      for (const ink of INKS) {
        it(`${theme}: ${ink} on ${ground}`, () => {
          const ratio = contrast(palette[ink][theme], palette[ground][theme]);
          expect(ratio).toBeGreaterThanOrEqual(4.5);
        });
      }
    }
  }

  it("light: the accent button's label clears its own fill", () => {
    expect(contrast(palette.paper.light, palette.accent.light)).toBeGreaterThanOrEqual(4.5);
  });

  it("dark: the accent button's label clears its own fill", () => {
    expect(contrast(palette.paper.dark, palette.accent.dark)).toBeGreaterThanOrEqual(4.5);
  });

  it("`border.control` clears 3:1, because it bounds real controls", () => {
    for (const theme of THEMES) {
      expect(contrast(palette.ink3[theme], palette.paper[theme])).toBeGreaterThanOrEqual(3);
    }
  });
});

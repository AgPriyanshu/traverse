import { axe } from "jest-axe";
import type { JestAxe } from "jest-axe";

/**
 * `jest-axe` ships a Jest matcher; this project runs Vitest. `expect.extend`
 * (`tests/setup.ts`) wires the runtime matcher in for every test file, but
 * TypeScript only knows about it through Jest's own `Matchers` interface —
 * this augments Vitest's instead, once, here, rather than adding an
 * `// @ts-expect-error` to every screen's axe test.
 */
declare module "vitest" {
  interface Assertion {
    toHaveNoViolations(): void;
  }
}

export const runAxe: JestAxe = axe;

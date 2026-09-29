import { axe } from "jest-axe";
import type { JestAxe } from "jest-axe";
import { expect } from "vitest";

export const runAxe: JestAxe = axe;

/**
 * `jest-axe` ships a Jest matcher; this project runs Vitest. `expect.extend`
 * (`tests/setup.ts`) wires the runtime matcher in for every test file, but
 * augmenting Vitest's own `Assertion` interface to type it hits a real
 * conflict with `@testing-library/jest-dom`'s own augmentation of the same
 * interface under this project's installed versions (`TS2428: All
 * declarations of 'Assertion' must have identical type parameters` — the two
 * packages' ambient declarations don't agree, and matching one exactly still
 * broke against the other). A cast at the one place the matcher is actually
 * called avoids the merge entirely.
 */
export const expectNoAxeViolations = async (container: Element): Promise<void> => {
  const results = await runAxe(container);
  (expect(results) as unknown as { toHaveNoViolations(): void }).toHaveNoViolations();
};

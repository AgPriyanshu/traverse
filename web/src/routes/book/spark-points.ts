import type { SparkPoint } from "./sparkline-bars";

export const toPoints = (histogram: Record<string, number>): SparkPoint[] => {
  const entries = Object.entries(histogram);
  entries.sort(([keyA], [keyB]) => {
    const numberA = Number(keyA);
    const numberB = Number(keyB);
    const isNumberA = Number.isFinite(numberA);
    const isNumberB = Number.isFinite(numberB);
    if (isNumberA && isNumberB) { return numberA - numberB; }
    if (isNumberA) { return -1; }
    if (isNumberB) { return 1; }
    return keyA.localeCompare(keyB);
  });
  return entries.map(([key, value]) => ({
    key,
    label: Number.isFinite(Number(key)) ? `Chapter ${key}` : "Unplaced mentions",
    value,
  }));
};

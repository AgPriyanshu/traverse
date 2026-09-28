import { createContext, useContext } from "react";
import type { ReadingPositionState } from "@/lib/use-reading-position";

export const ReadingPositionContext = createContext<ReadingPositionState | null>(null);

/** Throws outside a `<ReadingPositionProvider>` — every project screen is expected to sit under one. */
export const useReadingPositionContext = (): ReadingPositionState => {
  const context = useContext(ReadingPositionContext);
  if (context === null) {
    throw new Error("useReadingPositionContext must be used within a ReadingPositionProvider");
  }
  return context;
};

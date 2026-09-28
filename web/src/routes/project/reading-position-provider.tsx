import type { ReactNode } from "react";
import type { Book } from "@/lib/api";
import { useReadingPosition } from "@/lib/use-reading-position";
import { ReadingPositionContext } from "./reading-position-context";

export type ReadingPositionProviderProps = {
  projectId: string;
  books: readonly Book[];
  children: ReactNode;
};

/**
 * Makes one project's reading position available to every screen under
 * `<ProjectLayout>` — characters, the graph, and the project-scoped ask all
 * read the same slider rather than each re-deriving their own (S8.6).
 */
export const ReadingPositionProvider = ({ projectId, books, children }: ReadingPositionProviderProps) => {
  const state = useReadingPosition(projectId, books);
  return <ReadingPositionContext.Provider value={state}>{children}</ReadingPositionContext.Provider>;
};

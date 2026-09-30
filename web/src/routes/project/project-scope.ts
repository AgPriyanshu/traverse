import { createContext, useContext } from "react";
import { useParams } from "react-router";

export type ProjectScope = {
  projectId: string;
  /** Where this scope's characters and graph live, so links stay inside it. */
  basePath: string;
  /** Set when the scope is one book of the project. */
  bookId: string | null;
  bookOrder: number | null;
};

export const ProjectScopeContext = createContext<ProjectScope | null>(null);

/**
 * The characters and graph screens render under two parents: a project, and
 * one book of it. Without a provider the scope is the project in the URL, so
 * `/projects/:projectId/...` needs no wrapper.
 */
export const useProjectScope = (): ProjectScope => {
  const context = useContext(ProjectScopeContext);
  const { projectId = "" } = useParams();

  if (context !== null) { return context; }
  return { projectId, basePath: `/projects/${projectId}`, bookId: null, bookOrder: null };
};

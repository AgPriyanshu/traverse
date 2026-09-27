import { useParams } from "react-router";
import { ErrorState, LoadingSkeleton } from "@/components/ui";
import { useProject } from "@/lib/api";
import { AskScreen } from "../ask/ask-screen";
import type { AskScope } from "../ask/types";

/** A project-scoped ask — the whole series, no reading-position limit. */
export const ProjectAsk = () => {
  // Hooks.
  const { projectId = "" } = useParams();

  // Apis.
  const project = useProject(projectId);

  // Early returns.
  if (project.isPending) {
    return <LoadingSkeleton label="Loading" />;
  }
  if (project.error) {
    return <ErrorState error={project.error} onRetry={() => void project.refetch()} />;
  }

  const scope: AskScope = {
    projectId,
    limitBookOrder: null,
    limitChapter: null,
    label: `the whole of ${project.data.name}`,
  };

  return <AskScreen scope={scope} heading={`Ask about ${project.data.name}`} />;
};

export default ProjectAsk;

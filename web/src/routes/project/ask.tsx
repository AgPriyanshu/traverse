import { useParams, useSearchParams } from "react-router";
import { ErrorState, LoadingSkeleton } from "@/components/ui";
import { useProject } from "@/lib/api";
import { AskScreen } from "../ask/ask-screen";
import type { AskScope } from "../ask/types";
import { useReadingPositionContext } from "./reading-position-context";

/**
 * A project-scoped ask, gated by the persistent reading-position slider in
 * `<ProjectLayout>` (S8.6) — "the whole series" is what the slider says it is,
 * never a silent, ungated default.
 */
export const ProjectAsk = () => {
  // Hooks.
  const { projectId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const autoAskQuestion = searchParams.get("q") ?? undefined;

  // Context.
  const { position, label: positionLabel } = useReadingPositionContext();

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
    limitBookOrder: position?.bookOrder ?? null,
    limitChapter: position?.chapter ?? null,
    label: position === null ? `the whole of ${project.data.name}` : `${project.data.name} — ${positionLabel.toLowerCase()}`,
  };

  return (
    <AskScreen
      scope={scope}
      heading={`Ask about ${project.data.name}`}
      autoAskQuestion={autoAskQuestion}
    />
  );
};

export default ProjectAsk;

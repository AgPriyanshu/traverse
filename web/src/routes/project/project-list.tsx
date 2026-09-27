import { Box, Button, HStack, Heading, SimpleGrid, Stack, Text } from "@chakra-ui/react";
import { useMemo } from "react";
import { Link as RouterLink } from "react-router";
import { PageHeader } from "@/components/layout";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui";
import type { Project } from "@/lib/api";
import { useProjects } from "@/lib/api";
import { formatCount, formatRelativeTime } from "@/lib/format";

const NewProjectButton = () => {
  return (
    <Button
      asChild
      size="sm"
      bg="accent.solid"
      color="accent.contrast"
      borderRadius="md"
      _hover={{ opacity: 0.9 }}
    >
      <RouterLink to="/projects/new">New project</RouterLink>
    </Button>
  );
};

/** A decorative spine strip — one bar per book. `aria-hidden`, since the visible book count beside it already says the same thing as text. */
const SpineStrip = ({ count }: { count: number }) => {
  const bars = Math.min(count, 12);
  return (
    <HStack gap="0.5" aria-hidden="true" height="8">
      {Array.from({ length: Math.max(bars, 1) }, (_unused, index) => (
        <Box
          key={index}
          width="1.5"
          height={bars === 0 ? "3" : `${5 + ((index * 3) % 4)}`}
          bg={count === 0 ? "bg.sunken" : "relation.kinship"}
          opacity={count === 0 ? 1 : 0.55 + (index % 3) * 0.15}
          borderRadius="1px"
        />
      ))}
    </HStack>
  );
};

const ProjectCard = ({ project }: { project: Project }) => {
  return (
    <Box
      asChild
      borderWidth="1px"
      borderColor="border"
      borderRadius="lg"
      bg="bg.surface"
      padding="5"
      transitionProperty="border-color, box-shadow"
      transitionDuration="fast"
      _hover={{ borderColor: "border.control", boxShadow: "card" }}
    >
      <RouterLink to={`/projects/${project.id}`}>
        <Stack gap="3" height="full">
          <Text textStyle="data" color="fg.subtle" textTransform="capitalize">
            {project.kind}
          </Text>

          <Heading as="h3" textStyle="subheading" color="fg" truncate>
            {project.name}
          </Heading>

          <SpineStrip count={project.book_count} />

          <Text textStyle="data" color="fg.subtle">
            {[
              formatCount(project.book_count, "book"),
              formatCount(project.character_count, "character"),
              formatCount(project.relation_count, "relationship"),
            ].join("  ·  ")}
          </Text>

          {project.updated_at ? (
            <Text textStyle="data" color="fg.subtle" borderTopWidth="1px" borderColor="border" paddingBlockStart="3">
              updated {formatRelativeTime(project.updated_at)}
            </Text>
          ) : null}
        </Stack>
      </RouterLink>
    </Box>
  );
};

export const ProjectList = () => {
  // Apis.
  const projects = useProjects();

  // useMemos.
  const sorted = useMemo(
    () => [...(projects.data ?? [])].sort((a, b) => a.name.localeCompare(b.name)),
    [projects.data],
  );

  return (
    <>
      <PageHeader
        title="Projects"
        description="A standalone novel or a series — Traverse reconciles the cast across every book in it."
        meta={sorted.length > 0 ? formatCount(sorted.length, "project") : undefined}
        actions={<NewProjectButton />}
      />

      {projects.isPending ? <LoadingSkeleton variant="cards" count={3} /> : null}

      {!projects.isPending && projects.error ? (
        <ErrorState error={projects.error} onRetry={() => void projects.refetch()} />
      ) : null}

      {!projects.isPending && !projects.error && sorted.length === 0 ? (
        <EmptyState
          title="No projects yet — create one to begin"
          description="A standalone project holds one novel. A series holds several, and every returning character keeps one row across all of them."
          action={<NewProjectButton />}
        />
      ) : null}

      {sorted.length > 0 ? (
        <SimpleGrid columns={{ base: 1, sm: 2, lg: 3 }} gap="4">
          {sorted.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </SimpleGrid>
      ) : null}
    </>
  );
};

export default ProjectList;

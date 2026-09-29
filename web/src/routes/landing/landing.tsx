import { Badge, Button, HStack, Heading, Link as ChakraLink, SimpleGrid, Stack, Text } from "@chakra-ui/react";
import { useMemo } from "react";
import { useNavigate, Link as RouterLink } from "react-router";
import { EmptyState, ErrorState, LoadingSkeleton, StatusDot } from "@/components/ui";
import { useProjects } from "@/lib/api";
import type { Project } from "@/lib/api";
import { formatCount } from "@/lib/format";
import { SuggestedQuestions } from "@/routes/ask/suggested-questions";

/**
 * PRD §9.1: "public URL, no signup, pre-seeded with the public-domain
 * corpus. Landing state offers three questions ... so a skimmer gets value
 * in one click." This is UI/UX only — it renders against whatever project
 * data already exists (`make seed`'s demo corpus in a real deployment, an
 * empty instance in a fresh checkout) rather than assuming a specific demo
 * project is always present.
 */
const featuredProjectFor = (projects: readonly Project[]): Project | null => {
  if (projects.length === 0) { return null; }
  const prideAndPrejudice = projects.find((project) => /pride.?and.?prejudice/i.test(project.slug));
  if (prideAndPrejudice) { return prideAndPrejudice; }

  return [...projects].sort((a, b) => b.character_count - a.character_count)[0] ?? null;
};

export const Landing = () => {
  // Hooks.
  const navigate = useNavigate();

  // Apis.
  const projects = useProjects();

  // useMemos.
  const featured = useMemo(() => featuredProjectFor(projects.data ?? []), [projects.data]);

  // Handlers.
  const handleAsk = (question: string) => {
    if (!featured) { return; }
    void navigate(`/projects/${featured.id}/ask?q=${encodeURIComponent(question)}`);
  };

  return (
    <Stack gap="10">
      <Stack gap="3" maxW="measure">
        <Text textStyle="data" color="accent.fg" textTransform="uppercase" letterSpacing="0.08em">
          Traverse
        </Text>
        <Heading as="h1" textStyle="display">
          Ask a novel anything. Get an answer with the page that proves it.
        </Heading>
        <Text textStyle="body" color="fg.muted">
          Traverse reads a book once — the cast, how everyone knows everyone
          else, what happens and when — then answers plain-English questions
          with a citation to the exact page.
        </Text>
      </Stack>

      {projects.isPending ? <LoadingSkeleton variant="cards" count={1} /> : null}
      {!projects.isPending && projects.error ? (
        <ErrorState error={projects.error} onRetry={() => void projects.refetch()} />
      ) : null}

      {!projects.isPending && !projects.error && featured ? (
        <Stack
          gap="5"
          borderWidth="1px"
          borderColor="border"
          borderRadius="lg"
          bg="bg.surface"
          padding="6"
        >
          <HStack justify="space-between" wrap="wrap" gap="3">
            <Stack gap="1">
              <HStack gap="2" wrap="wrap">
                <Heading as="h2" textStyle="subheading">{featured.name}</Heading>
                <Badge variant="outline" size="sm">Read-only demo</Badge>
              </HStack>
              <Text textStyle="small" color="fg.muted">
                {formatCount(featured.character_count, "character")} · {formatCount(featured.relation_count, "relationship")} · seeded from the public-domain corpus
              </Text>
            </Stack>
          </HStack>

          <SuggestedQuestions projectId={featured.id} onAsk={handleAsk} />

          <HStack gap="4" wrap="wrap">
            <ChakraLink asChild textStyle="small" color="accent.fg">
              <RouterLink to={`/projects/${featured.id}/graph`}>Explore the relationship graph</RouterLink>
            </ChakraLink>
            <ChakraLink asChild textStyle="small" color="accent.fg">
              <RouterLink to={`/projects/${featured.id}`}>Browse this project</RouterLink>
            </ChakraLink>
          </HStack>
        </Stack>
      ) : null}

      {!projects.isPending && !projects.error && !featured ? (
        <EmptyState
          eyebrow="No demo corpus loaded yet"
          title="Upload a book to see Traverse work"
          description="This instance has no seeded project yet. Upload a PDF novel and Traverse will build its cast and relationship graph from scratch."
          action={
            <Button asChild bg="accent.solid" color="accent.contrast" borderRadius="md" _hover={{ opacity: 0.9 }}>
              <RouterLink to="/books/upload">Upload your first book</RouterLink>
            </Button>
          }
        />
      ) : null}

      <SimpleGrid columns={{ base: 1, sm: 2 }} gap="4">
        <Stack
          gap="2"
          borderWidth="1px"
          borderColor="border"
          borderRadius="lg"
          bg="bg.sunken"
          padding="5"
        >
          <StatusDot tone="ok" label="Seeded books are read-only" />
          <Text textStyle="small" color="fg.muted">
            The demo corpus above is public-domain and shared by every
            visitor — nobody can edit or delete it from here.
          </Text>
        </Stack>

        <Stack
          gap="2"
          borderWidth="1px"
          borderColor="border"
          borderRadius="lg"
          bg="bg.sunken"
          padding="5"
        >
          <StatusDot tone="warn" label="Want to try your own book?" />
          <Text textStyle="small" color="fg.muted">
            The upload sandbox takes one PDF, up to 150 pages, and deletes it
            automatically after 24 hours.
          </Text>
          <ChakraLink asChild textStyle="small" color="accent.fg">
            <RouterLink to="/books/upload">Try the upload sandbox</RouterLink>
          </ChakraLink>
        </Stack>
      </SimpleGrid>

      <ChakraLink asChild textStyle="small" color="fg.muted">
        <RouterLink to="/books">See every book in the library instead</RouterLink>
      </ChakraLink>
    </Stack>
  );
};

export default Landing;

import { Button, HStack, Stack, Text } from "@chakra-ui/react";
import { useMemo } from "react";
import { useCharacters, useProject } from "@/lib/api";
import { limitsForProject } from "@/lib/reading-position";
import { TIER_ORDER } from "@/routes/project/character-labels";

export type SuggestedQuestionsProps = {
  projectId: string;
  onAsk: (question: string) => void;
};

const GENERIC_QUESTIONS = [
  "Who are the main characters?",
  "How do the two leads first meet?",
  "What happens in the opening chapters?",
];

/**
 * A skimming visitor gets value in one click (PRD §9.1). Derived from the
 * project's own roster when it has loaded; the three generic prompts above
 * are the fallback while it hasn't (or for a project with no roster yet) —
 * never a blank landing state.
 */
export const SuggestedQuestions = ({ projectId, onAsk }: SuggestedQuestionsProps) => {
  // Apis.
  const project = useProject(projectId);
  const { limitBookOrder } = limitsForProject(null, project.data?.books ?? []);
  const characters = useCharacters(project.data ? projectId : undefined, {
    limit_book_order: limitBookOrder,
  });

  // useMemos.
  const questions = useMemo(() => {
    const roster = characters.data ?? [];
    if (roster.length === 0) { return GENERIC_QUESTIONS; }

    const ranked = [...roster].sort(
      (a, b) =>
        TIER_ORDER.indexOf(a.importance_tier) - TIER_ORDER.indexOf(b.importance_tier) ||
        b.mention_count - a.mention_count,
    );
    const [first, second, third] = ranked;

    const built: string[] = [];
    if (first) { built.push(`Who is ${first.canonical_name}?`); }
    if (first && second) {
      built.push(`How does ${first.canonical_name} know ${second.canonical_name}?`);
    }
    if (third) { built.push(`What happens to ${third.canonical_name}?`); }
    return built.length > 0 ? built : GENERIC_QUESTIONS;
  }, [characters.data]);

  return (
    <Stack gap="3">
      <Text textStyle="small" color="fg.subtle">
        Try asking
      </Text>
      <HStack gap="2" wrap="wrap" role="group" aria-label="Suggested questions">
        {questions.map((question) => (
          <Button
            key={question}
            size="sm"
            variant="outline"
            borderColor="border.control"
            color="fg"
            borderRadius="md"
            onClick={() => { onAsk(question); }}
          >
            {question}
          </Button>
        ))}
      </HStack>
    </Stack>
  );
};

import { HStack, Stack, Text } from "@chakra-ui/react";
import { FamilyStroke } from "./family-stroke";
import { FAMILY_LABEL, FAMILY_LINE_NAME, FAMILY_ORDER } from "./relation-style";

export const GraphLegend = () => {
  return (
    <Stack
      as="section"
      aria-label="Legend"
      gap="2"
      bg="bg.sunken"
      borderRadius="lg"
      paddingBlock="3"
      paddingInline="4"
    >
      <HStack gap={{ base: "3", md: "5" }} wrap="wrap">
        {FAMILY_ORDER.map((family) => (
          <HStack key={family} gap="2">
            <FamilyStroke family={family} width={36} />
            <Text textStyle="small" color="fg">
              {FAMILY_LABEL[family]}
              <Text as="span" color="fg.muted">
                {" "}
                · {FAMILY_LINE_NAME[family]}
              </Text>
            </Text>
          </HStack>
        ))}
      </HStack>
      <Text textStyle="small" color="fg.muted">
        Heavier lines carry more citations. Larger nodes are more important characters.
        An arrowhead points at the object of the relation.
      </Text>
    </Stack>
  );
};

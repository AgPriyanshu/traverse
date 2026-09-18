import { Box, Flex, Heading, Stack, Text } from "@chakra-ui/react";
import type { ReactNode } from "react";

export type PageHeaderProps = {
  title: string;
  /** A short line above the title — a project name, a series, a section. */
  eyebrow?: ReactNode;
  description?: string;
  /** Counts, status, timestamps. Rendered under the title in data type. */
  meta?: ReactNode;
  actions?: ReactNode;
};

export const PageHeader = ({
  title,
  eyebrow,
  description,
  meta,
  actions,
}: PageHeaderProps) => {
  return (
    <Box
      as="header"
      paddingBlockEnd="6"
      marginBlockEnd="6"
      borderBottomWidth="1px"
      borderColor="border"
    >
      <Flex
        gap="4"
        align={{ base: "stretch", sm: "flex-end" }}
        justify="space-between"
        direction={{ base: "column", sm: "row" }}
      >
        <Stack gap="2" minW="0">
          {eyebrow ? (
            <Box textStyle="data" color="fg.subtle">
              {eyebrow}
            </Box>
          ) : null}
          <Heading as="h1" textStyle="display" color="fg">
            {title}
          </Heading>
          {description ? (
            <Text textStyle="body" color="fg.muted" maxW="measure">
              {description}
            </Text>
          ) : null}
          {meta ? <Box paddingBlockStart="1">{meta}</Box> : null}
        </Stack>

        {actions ? <Box flexShrink="0">{actions}</Box> : null}
      </Flex>
    </Box>
  );
};

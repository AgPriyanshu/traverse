import { Box, Flex, HStack, Span } from "@chakra-ui/react";
import { Link as RouterLink } from "react-router";
import { ColorModeToggle } from "@/components/ui/color-mode-toggle";
import { HealthIndicator } from "./health-indicator";
import { NavLinks } from "./nav-links";
import { PRIMARY_NAV } from "./nav-items";

export const TopBar = () => {
  return (
    <Box
      as="header"
      position="sticky"
      top="0"
      zIndex="10"
      bg="bg.surface"
      borderBottomWidth="1px"
      borderColor="border"
    >
      <Flex
        maxW="shell"
        marginInline="auto"
        paddingInline={{ base: "4", md: "6" }}
        paddingBlock="3"
        align="center"
        justify="space-between"
        gap="4"
      >
        <RouterLink to="/books" aria-label="Traverse — go to the library">
          <HStack gap="2.5">
            <Box
              width="2.5"
              height="2.5"
              bg="accent.solid"
              borderRadius="sm"
              aria-hidden="true"
            />
            <Span
              fontFamily="heading"
              fontSize="subheading"
              fontWeight="500"
              letterSpacing="0.01em"
              color="fg"
            >
              Traverse
            </Span>
          </HStack>
        </RouterLink>

        <HStack gap="1">
          <HealthIndicator />
          <ColorModeToggle />
        </HStack>
      </Flex>

      {/* The side nav is desktop-only, so the same links live here below md. */}
      <Box
        hideFrom="md"
        borderTopWidth="1px"
        borderColor="border"
        paddingInline="4"
        paddingBlock="2"
      >
        <NavLinks
          items={PRIMARY_NAV.flatMap((section) => section.items)}
          direction="row"
          ariaLabel="Primary"
        />
      </Box>
    </Box>
  );
};

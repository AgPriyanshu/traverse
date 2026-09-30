import { Box, Flex, HStack, Span } from "@chakra-ui/react";
import { Link as RouterLink } from "react-router";
import { ColorModeToggle } from "@/components/ui/color-mode-toggle";
import { HealthIndicator } from "./health-indicator";
import { InferenceModeIndicator } from "./inference-mode-indicator";
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
            <Box asChild color="accent.solid" flexShrink="0">
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <rect x="2.5" y="4" width="4" height="16" rx="1" />
                <path d="M2.5 8.5h4M2.5 15.5h4" />
                <rect x="8.5" y="4" width="4" height="16" rx="1" />
                <path d="M8.5 8.5h4" />
                <rect x="16.3" y="5.5" width="4" height="14.5" rx="1" transform="rotate(-10 18.3 12.75)" />
              </svg>
            </Box>
            <Span
              fontFamily="heading"
              fontSize="subheading"
              fontWeight="600"
              letterSpacing="-0.01em"
              color="accent.solid"
            >
              Traverse
            </Span>
          </HStack>
        </RouterLink>

        <HStack gap="1" wrap="wrap" justify="flex-end">
          <InferenceModeIndicator />
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

import { Box, Stack, Text } from "@chakra-ui/react";
import { NavLinks } from "./nav-links";
import { PRIMARY_NAV } from "./nav-items";

export const SideNav = () => {
  return (
    <Box
      as="aside"
      hideBelow="md"
      width="sidenav"
      flexShrink="0"
      borderRightWidth="1px"
      borderColor="border"
      paddingBlock="7"
      paddingInline="3"
    >
      <Stack gap="6" position="sticky" top="20">
        {PRIMARY_NAV.map((section) => (
          <Stack key={section.heading} gap="2">
            <Text
              textStyle="data"
              color="fg.subtle"
              paddingInline="2.5"
              textTransform="lowercase"
              letterSpacing="0.06em"
            >
              {section.heading}
            </Text>
            <NavLinks items={section.items} ariaLabel={section.heading} />
          </Stack>
        ))}
      </Stack>
    </Box>
  );
};

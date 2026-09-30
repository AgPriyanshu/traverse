import { Box, Heading, Stack } from "@chakra-ui/react";
import { PRIMARY_NAV } from "./nav-items";
import { NavLinks } from "./nav-links";

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
            {/* Not a heading: the group is already labelled via NavLinks' aria-label, and a second "Library" heading duplicates the page's own h1 in the outline. */}
            <Heading
              as="p"
              color="fg.subtle"
              paddingInline="2.5"
              cursor={"default"}
            >
              {section.heading}
            </Heading>
            <NavLinks items={section.items} ariaLabel={section.heading} />
          </Stack>
        ))}
      </Stack>
    </Box>
  );
};

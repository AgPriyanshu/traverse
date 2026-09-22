import { Box, Flex } from "@chakra-ui/react";
import { Outlet } from "react-router";
import { AppToaster } from "@/components/ui";
import { SideNav } from "./side-nav";
import { SkipLink } from "./skip-link";
import { TopBar } from "./top-bar";

export const AppShell = () => {
  return (
    <Flex direction="column" minHeight="100dvh" bg="bg">
      <AppToaster />
      <SkipLink />
      <TopBar />

      <Flex
        flex="1"
        width="full"
        maxW="shell"
        marginInline="auto"
        align="stretch"
      >
        <SideNav />

        <Box
          as="main"
          id="main"
          flex="1"
          minWidth="0"
          paddingInline={{ base: "4", md: "7" }}
          paddingBlock={{ base: "6", md: "9" }}
        >
          <Outlet />
        </Box>
      </Flex>
    </Flex>
  );
};

import { ChakraProvider } from "@chakra-ui/react";
import { ThemeProvider } from "next-themes";
import type { PropsWithChildren } from "react";
import { system } from "./theme";

export const DesignSystemProvider = ({ children }: PropsWithChildren) => {
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      <ChakraProvider value={system}>{children}</ChakraProvider>
    </ThemeProvider>
  );
};

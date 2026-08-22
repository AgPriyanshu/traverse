import { ChakraProvider } from "@chakra-ui/react";
import { ThemeProvider } from "next-themes";
import type { PropsWithChildren } from "react";
import { system } from "./theme";

export const DesignSystemProvider = ({ children }: PropsWithChildren) => {
  return (
    <ChakraProvider value={system}>
      <ThemeProvider attribute="class" disableTransitionOnChange>
        {children}
      </ThemeProvider>
    </ChakraProvider>
  );
};

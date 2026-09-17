import { useTheme } from "next-themes";

export type ColorMode = "light" | "dark";

export const useColorMode = () => {
  // Hooks.
  const { resolvedTheme, setTheme, theme } = useTheme();

  // Variables.
  const colorMode: ColorMode = resolvedTheme === "dark" ? "dark" : "light";

  // Handlers.
  const toggleColorMode = () => {
    setTheme(colorMode === "dark" ? "light" : "dark");
  };

  return {
    colorMode,
    followsSystem: theme === "system",
    setTheme,
    toggleColorMode,
  };
};

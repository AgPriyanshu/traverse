import { IconButton } from "@chakra-ui/react";
import { useColorMode } from "@/design-system/use-color-mode";
import { useHydrated } from "@/lib/use-hydrated";
import { MoonIcon, SunIcon } from "./icons";

/**
 * The resolved theme is unknown until the client hydrates, so the control
 * renders inert first — labelling it "Dark" before the class lands would
 * announce the wrong thing.
 */
export const ColorModeToggle = () => {
  // Hooks.
  const hydrated = useHydrated();
  const { colorMode, toggleColorMode } = useColorMode();

  // Variables.
  const nextMode = colorMode === "dark" ? "light" : "dark";
  const label = hydrated ? `Switch to ${nextMode} theme` : "Switch theme";

  return (
    <IconButton
      aria-label={label}
      title={label}
      variant="ghost"
      size="sm"
      color="fg.muted"
      borderRadius="md"
      _hover={{ bg: "bg.sunken", color: "fg" }}
      onClick={toggleColorMode}
    >
      {hydrated && colorMode === "dark" ? <SunIcon /> : <MoonIcon />}
    </IconButton>
  );
};

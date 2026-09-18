import { Link } from "@chakra-ui/react";

/** The first thing in the tab order, and invisible until it has focus. */
export const SkipLink = () => {
  return (
    <Link
      href="#main"
      position="absolute"
      insetInlineStart="4"
      top="-20"
      zIndex="20"
      bg="bg.surface"
      color="fg"
      textStyle="small"
      textDecoration="none"
      borderWidth="1px"
      borderColor="border.control"
      borderRadius="md"
      paddingInline="3"
      paddingBlock="2"
      _focusVisible={{ top: "3" }}
    >
      Skip to content
    </Link>
  );
};

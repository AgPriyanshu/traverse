import { Box, Wrap } from "@chakra-ui/react";
import { NavLink } from "react-router";
import type { NavItem } from "./nav-items";

export type NavLinksProps = {
  items: NavItem[];
  direction?: "row" | "column";
  ariaLabel: string;
};

export const NavLinks = ({
  items,
  direction = "column",
  ariaLabel,
}: NavLinksProps) => {
  return (
    <Box as="nav" aria-label={ariaLabel}>
      <Wrap
        gap={direction === "row" ? "1" : "0.5"}
        direction={direction === "row" ? "row" : "column"}
        align={direction === "row" ? "center" : "stretch"}
      >
        {items.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.match !== "prefix"}>
            {({ isActive }) => (
              <Box
                textStyle="small"
                fontWeight={isActive ? "500" : "400"}
                color={isActive ? "fg" : "fg.muted"}
                bg={isActive ? "bg.sunken" : "transparent"}
                borderRadius="md"
                paddingInline="2.5"
                paddingBlock="1.5"
                borderLeftWidth={direction === "column" ? "2px" : "0"}
                borderLeftColor={isActive ? "accent.solid" : "transparent"}
                borderBottomWidth={direction === "row" ? "2px" : "0"}
                borderBottomColor={isActive ? "accent.solid" : "transparent"}
                whiteSpace="nowrap"
                transitionProperty="color, background-color"
                transitionDuration="fast"
                _hover={{ color: "fg", bg: "bg.sunken" }}
              >
                {item.label}
              </Box>
            )}
          </NavLink>
        ))}
      </Wrap>
    </Box>
  );
};

import { HStack, Link, Text } from "@chakra-ui/react";
import { Link as RouterLink } from "react-router";
import type { AskScope } from "./types";

export type ScopeBannerProps = { scope: AskScope };

/**
 * Invisible carried context is confusing when it is wrong (frontend-1.md,
 * S6.13) — this is the reading-position scope the frontend itself chose
 * (`limit_book_order`/`limit_chapter`), always shown with a way to clear it.
 * It is not the router's carried *character* scope (S6.6) — no `QueryEvent`
 * surfaces which characters a follow-up resolved against yet (Sprint 6 SCR),
 * so that part of "about Elizabeth Bennet" isn't rendered until it does.
 */
export const ScopeBanner = ({ scope }: ScopeBannerProps) => {
  return (
    <HStack
      gap="3"
      wrap="wrap"
      borderWidth="1px"
      borderColor="border"
      borderRadius="md"
      bg="bg.sunken"
      paddingInline="3"
      paddingBlock="2"
    >
      <Text textStyle="small" color="fg.muted">
        Asking about {scope.label}.
      </Text>
      {scope.clearHref ? (
        <Link asChild textStyle="small" color="accent.fg">
          <RouterLink to={scope.clearHref}>Ask the whole series instead</RouterLink>
        </Link>
      ) : null}
    </HStack>
  );
};

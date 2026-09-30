import { Box, HStack, Link } from "@chakra-ui/react";
import { Link as RouterLink, useLocation } from "react-router";
import { useBook, useProject } from "@/lib/api";
import { useCurrentBreadcrumbLabel } from "./breadcrumb-label";

export type Crumb = {
  label: string;
  /** Absent on the page being shown. */
  to?: string;
};

const sectionCrumbs = (base: string, section: string | undefined, rest: string[], recordLabel: string | null): Crumb[] => {
  if (section === "characters") {
    const characters: Crumb = { label: "Characters", to: `${base}/characters` };
    return rest[0] === undefined ? [characters] : [characters, { label: recordLabel ?? "Character" }];
  }
  if (section === "pages" && rest[0] !== undefined) { return [{ label: `Page ${rest[0]}` }]; }
  if (section === "chapters") { return [{ label: "Chapters" }]; }
  if (section === "graph") { return [{ label: "Graph" }]; }
  if (section === "ask") { return [{ label: "Ask" }]; }
  if (section === "review") { return [{ label: "Review" }]; }
  return [];
};

/** The parents of the page being shown, from the URL. Top-level pages have none. */
const useTrail = (): Crumb[] => {
  // Hooks.
  const { pathname } = useLocation();
  const [root, first, section, ...rest] = pathname.split("/").filter(Boolean);

  // Variables.
  const isBook = root === "books" && first !== undefined && first !== "upload";
  const isProject = root === "projects" && first !== undefined && first !== "new";

  // Apis.
  const book = useBook(isBook ? first : undefined);
  const project = useProject(isProject ? first : undefined);

  // Context.
  const recordLabel = useCurrentBreadcrumbLabel();

  let trail: Crumb[] = [];
  if (root === "books" && first === "upload") {
    trail = [{ label: "Books", to: "/books" }, { label: "Add a book" }];
  } else if (isBook) {
    const base = `/books/${first}`;
    trail = [
      { label: "Books", to: "/books" },
      { label: book.data?.title ?? "Book", to: base },
      ...sectionCrumbs(base, section, rest, recordLabel),
    ];
  } else if (root === "projects" && first === "new") {
    trail = [{ label: "Projects", to: "/projects" }, { label: "New project" }];
  } else if (isProject) {
    const base = `/projects/${first}`;
    trail = [
      { label: "Projects", to: "/projects" },
      { label: project.data?.name ?? "Project", to: base },
      ...sectionCrumbs(base, section, rest, recordLabel),
    ];
  } else if (root === "ops" && first === "evals") {
    trail = [{ label: "Operations", to: "/ops" }, { label: "Evaluations" }];
  }

  return trail.map((crumb, index) => (index === trail.length - 1 ? { label: crumb.label } : crumb));
};

/** A back link to the parent page, with the trail that leads there. Shown on every sub page. */
export const Breadcrumbs = () => {
  // Hooks.
  const trail = useTrail();

  // Variables.
  const parent = trail.length > 1 ? trail[trail.length - 2] : undefined;

  // Early returns.
  if (parent?.to === undefined) { return null; }

  return (
    <Box as="nav" aria-label="Breadcrumb" marginBlockEnd="5">
      <HStack gap="2" align="center" textStyle="small" color="fg.muted" minWidth="0">
        <Link
          asChild
          display="inline-flex"
          alignItems="center"
          flexShrink="0"
          color="fg.muted"
          textDecoration="none"
          borderRadius="sm"
          _hover={{ color: "fg" }}
        >
          <RouterLink to={parent.to} aria-label={`Back to ${parent.label}`}>
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="m15 18-6-6 6-6" />
            </svg>
          </RouterLink>
        </Link>

        <Box as="ol" display="flex" flexWrap="wrap" alignItems="center" gap="2" listStyleType="none" margin="0" padding="0" minWidth="0">
          {trail.map((crumb, index) => {
            const isLast = index === trail.length - 1;
            return (
              <Box as="li" key={`${index}-${crumb.label}`} display="flex" alignItems="center" gap="2" minWidth="0">
                {crumb.to !== undefined ? (
                  <Link asChild color="fg.muted" textDecoration="none" _hover={{ color: "fg", textDecoration: "underline" }}>
                    <RouterLink to={crumb.to}>{crumb.label}</RouterLink>
                  </Link>
                ) : (
                  <Box as="span" aria-current={isLast ? "page" : undefined} color="fg" fontWeight="500" truncate maxW="32ch">
                    {crumb.label}
                  </Box>
                )}
                {isLast ? null : <Box as="span" aria-hidden="true" color="fg.subtle">/</Box>}
              </Box>
            );
          })}
        </Box>
      </HStack>
    </Box>
  );
};

import { Box } from "@chakra-ui/react";
import { Outlet, useParams } from "react-router";
import { NavLinks } from "@/components/layout";
import type { NavItem } from "@/components/layout";

const projectNav = (projectId: string): NavItem[] => [
  { to: `/projects/${projectId}`, label: "Overview", match: "exact" },
  { to: `/projects/${projectId}/characters`, label: "Characters", match: "prefix" },
  { to: `/projects/${projectId}/graph`, label: "Graph", match: "exact" },
  { to: `/projects/${projectId}/ask`, label: "Ask", match: "prefix" },
];

/** The tab nav shared by every screen scoped to one project — the series-wide equivalent of `<BookLayout>`. */
export const ProjectLayout = () => {
  // Hooks.
  const { projectId = "" } = useParams();

  return (
    <>
      <Box
        marginBlockEnd="7"
        paddingBlockEnd="1"
        borderBottomWidth="1px"
        borderColor="border"
      >
        <NavLinks items={projectNav(projectId)} direction="row" ariaLabel="This project" />
      </Box>

      <Outlet />
    </>
  );
};

export default ProjectLayout;

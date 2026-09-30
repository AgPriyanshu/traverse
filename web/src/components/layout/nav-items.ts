export type NavItem = {
  to: string;
  label: string;
  /** Matches nested routes too, rather than only the exact path. */
  match?: "exact" | "prefix";
};

export type NavSection = {
  heading: string;
  items: NavItem[];
};

export const PRIMARY_NAV: NavSection[] = [
  {
    heading: "Library",
    items: [{ to: "/books", label: "Books", match: "prefix" }],
  },
  {
    heading: "Projects",
    items: [{ to: "/projects", label: "Projects", match: "prefix" }],
  },
  {
    heading: "System",
    items: [{ to: "/ops", label: "Operations", match: "prefix" }],
  },
];

/** Characters and the graph render inside the book, narrowed to it, so the book's header and tabs stay put. */
export const bookNav = (bookId: string, projectId: string | undefined): NavItem[] => {
  const items: NavItem[] = [
    { to: `/books/${bookId}`, label: "Overview", match: "exact" },
    { to: `/books/${bookId}/chapters`, label: "Chapters", match: "prefix" },
  ];

  if (projectId) {
    items.push(
      { to: `/books/${bookId}/characters`, label: "Characters", match: "prefix" },
      { to: `/books/${bookId}/graph`, label: "Graph", match: "exact" },
    );
  }
  items.push(
    { to: `/books/${bookId}/ask`, label: "Ask", match: "prefix" },
    { to: `/books/${bookId}/review`, label: "Review", match: "prefix" },
  );
  return items;
};

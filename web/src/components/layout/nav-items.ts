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
    items: [
      { to: "/books", label: "Books", match: "exact" },
      { to: "/books/upload", label: "Add a book", match: "exact" },
    ],
  },
  {
    heading: "Projects",
    items: [
      { to: "/projects", label: "Projects", match: "exact" },
      { to: "/projects/new", label: "New project", match: "exact" },
    ],
  },
  {
    heading: "System",
    items: [{ to: "/ops", label: "Operations", match: "prefix" }],
  },
];

/**
 * Characters and the graph moved to project scope in S5 — a book can be one
 * of several volumes reconciled into one roster, so those two links leave
 * the book's own nav and point at the project, book-filtered
 * (`?book=<bookId>`) so arriving from a specific book still lands somewhere
 * relevant rather than the whole series unfiltered.
 */
export const bookNav = (
  bookId: string,
  projectId: string | undefined,
  bookSeriesOrder?: number | null,
): NavItem[] => {
  const items: NavItem[] = [
    { to: `/books/${bookId}`, label: "Overview", match: "exact" },
    { to: `/books/${bookId}/chapters`, label: "Chapters", match: "prefix" },
  ];
  if (projectId) {
    const graphQuery =
      bookSeriesOrder !== null && bookSeriesOrder !== undefined ? `?book=${bookSeriesOrder}` : "";
    items.push(
      { to: `/projects/${projectId}/characters`, label: "Characters", match: "exact" },
      { to: `/projects/${projectId}/graph${graphQuery}`, label: "Graph", match: "exact" },
    );
  }
  items.push(
    { to: `/books/${bookId}/ask`, label: "Ask", match: "prefix" },
    { to: `/books/${bookId}/review`, label: "Review", match: "prefix" },
  );
  return items;
};

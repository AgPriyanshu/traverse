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
    heading: "System",
    items: [{ to: "/ops", label: "Operations", match: "prefix" }],
  },
];

export const bookNav = (bookId: string): NavItem[] => [
  { to: `/books/${bookId}`, label: "Overview", match: "exact" },
  { to: `/books/${bookId}/chapters`, label: "Chapters", match: "prefix" },
  { to: `/books/${bookId}/characters`, label: "Characters", match: "prefix" },
  { to: `/books/${bookId}/graph`, label: "Graph", match: "prefix" },
  { to: `/books/${bookId}/ask`, label: "Ask", match: "prefix" },
  { to: `/books/${bookId}/review`, label: "Review", match: "prefix" },
];

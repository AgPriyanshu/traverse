import { Navigate } from "react-router";
import type { RouteObject } from "react-router";
import { AppShell } from "@/components/layout";
import { NotYetBuilt } from "@/components/ui";
import { NotFound } from "./not-found";
import { RouteError } from "./route-error";

/**
 * The whole Sprint 1–9 surface is declared now. A route added later is a
 * refactor; a route stubbed now is a one-line swap — so unbuilt screens render
 * `<NotYetBuilt>` rather than being left out of the table.
 */
export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <Navigate to="/books" replace /> },

      {
        path: "books",
        children: [
          {
            index: true,
            lazy: async () => ({
              Component: (await import("./books/library")).Library,
            }),
          },
          {
            path: "upload",
            lazy: async () => ({
              Component: (await import("./books/upload")).Upload,
            }),
          },
          {
            path: ":bookId",
            lazy: async () => ({
              Component: (await import("./book/book-layout")).BookLayout,
            }),
            children: [
              {
                index: true,
                lazy: async () => ({
                  Component: (await import("./book/overview")).BookOverview,
                }),
              },
              {
                path: "chapters",
                lazy: async () => ({
                  Component: (await import("./book/chapters")).Chapters,
                }),
              },
              {
                path: "pages/:page",
                element: <NotYetBuilt screen="The page viewer" sprint={2} />,
              },
              {
                path: "characters",
                element: <NotYetBuilt screen="The character roster" sprint={3} />,
              },
              {
                path: "characters/:characterId",
                element: <NotYetBuilt screen="Character detail" sprint={3} />,
              },
              {
                path: "graph",
                element: <NotYetBuilt screen="The graph explorer" sprint={4} />,
              },
              {
                path: "ask",
                element: <NotYetBuilt screen="Ask" sprint={6} />,
              },
              {
                path: "review",
                element: <NotYetBuilt screen="The review queue" sprint={7} />,
              },
            ],
          },
        ],
      },

      {
        path: "projects",
        children: [
          { index: true, element: <NotYetBuilt screen="Projects" sprint={5} /> },
          { path: "new", element: <NotYetBuilt screen="New project" sprint={5} /> },
          {
            path: ":projectId",
            children: [
              {
                index: true,
                element: <NotYetBuilt screen="Project overview" sprint={5} />,
              },
              {
                path: "characters",
                element: <NotYetBuilt screen="The series roster" sprint={5} />,
              },
              {
                path: "graph",
                element: <NotYetBuilt screen="The series graph" sprint={5} />,
              },
              {
                path: "ask",
                element: <NotYetBuilt screen="Ask" sprint={6} />,
              },
            ],
          },
        ],
      },

      {
        path: "ops",
        children: [
          {
            index: true,
            element: <NotYetBuilt screen="The operations dashboard" sprint={9} />,
          },
          {
            path: "evals",
            element: <NotYetBuilt screen="Eval ablations" sprint={8} />,
          },
        ],
      },

      { path: "*", element: <NotFound /> },
    ],
  },
]

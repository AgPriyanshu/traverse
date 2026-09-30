import type { RouteObject } from "react-router";
import { AppShell } from "@/components/layout";
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
      {
        index: true,
        lazy: async () => ({
          Component: (await import("./landing/landing")).Landing,
        }),
      },

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
                lazy: async () => ({
                  Component: (await import("./book/page")).BookPage,
                }),
              },
              {
                lazy: async () => ({
                  Component: (await import("./book/book-cast-layout")).BookCastLayout,
                }),
                children: [
                  {
                    path: "characters",
                    lazy: async () => ({
                      Component: (await import("./project/characters")).Characters,
                    }),
                  },
                  {
                    path: "characters/:characterId",
                    lazy: async () => ({
                      Component: (await import("./project/character-detail")).CharacterDetail,
                    }),
                  },
                  {
                    path: "graph",
                    lazy: async () => ({
                      Component: (await import("./project/graph/graph-explorer")).GraphExplorer,
                    }),
                  },
                ],
              },
              {
                path: "ask",
                lazy: async () => ({
                  Component: (await import("./book/ask")).BookAsk,
                }),
              },
              {
                path: "review",
                lazy: async () => ({
                  Component: (await import("./book/review")).BookReview,
                }),
              },
            ],
          },
        ],
      },

      {
        path: "projects",
        children: [
          {
            index: true,
            lazy: async () => ({
              Component: (await import("./project/project-list")).ProjectList,
            }),
          },
          {
            path: "new",
            lazy: async () => ({
              Component: (await import("./project/project-new")).ProjectNew,
            }),
          },
          {
            path: ":projectId",
            lazy: async () => ({
              Component: (await import("./project/project-layout")).ProjectLayout,
            }),
            children: [
              {
                index: true,
                lazy: async () => ({
                  Component: (await import("./project/project-overview")).ProjectOverview,
                }),
              },
              {
                path: "characters",
                lazy: async () => ({
                  Component: (await import("./project/characters")).Characters,
                }),
              },
              {
                path: "characters/:characterId",
                lazy: async () => ({
                  Component: (await import("./project/character-detail")).CharacterDetail,
                }),
              },
              {
                path: "graph",
                lazy: async () => ({
                  Component: (await import("./project/graph/graph-explorer")).GraphExplorer,
                }),
              },
              {
                path: "ask",
                lazy: async () => ({
                  Component: (await import("./project/ask")).ProjectAsk,
                }),
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
            lazy: async () => ({
              Component: (await import("./ops/dashboard/ops-dashboard")).OpsDashboard,
            }),
          },
          {
            path: "evals",
            lazy: async () => ({
              Component: (await import("./ops/evals/evals-screen")).EvalsScreen,
            }),
          },
        ],
      },

      { path: "*", element: <NotFound /> },
    ],
  },
]

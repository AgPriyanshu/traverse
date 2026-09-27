import { render } from "@testing-library/react";
import type { RenderResult } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createMemoryRouter } from "react-router";
import type { DataRouter } from "react-router";
import { DesignSystemProvider } from "@/design-system/provider";
import { routes } from "@/routes/routes";

export type RenderRouteResult = RenderResult & {
  /** The underlying data router — for tests that drive navigation directly, e.g. `router.navigate(-1)` for a browser-back simulation. */
  router: DataRouter;
};

export const renderRoute = (path: string): RenderRouteResult => {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });

  const result = render(
    <DesignSystemProvider>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </DesignSystemProvider>,
  );

  return { ...result, router };
};

import { QueryClient } from "@tanstack/react-query";
import { isApiError } from "./errors";

const MAX_RETRIES = 2;

export const createQueryClient = () => {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // A 501 is the contract saying "not built yet" and a 4xx is the
        // contract saying "no". Retrying either just delays the error surface.
        retry: (failureCount, error) => {
          if (isApiError(error) && error.status < 500) { return false; }
          if (isApiError(error) && error.status === 501) { return false; }
          return failureCount < MAX_RETRIES;
        },
      },
      mutations: {
        retry: false,
      },
    },
  });
};

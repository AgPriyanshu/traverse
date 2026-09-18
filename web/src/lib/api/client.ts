import createClient from "openapi-fetch";
import { ApiError, NetworkError } from "./errors";
import type { paths } from "./schema";

/**
 * The page's own origin, so every request is same-origin: the API serves no
 * CORS headers, and `/api` is proxied by Vite in dev and by nginx in the
 * container. `VITE_API_BASE_URL` names that proxy target, not this.
 *
 * Absolute rather than "" because `fetch` outside a browser — a jsdom test,
 * a prerender — refuses to parse a relative URL.
 */
export const API_BASE_URL =
  typeof window === "undefined" ? "" : window.location.origin;

export const client = createClient<paths>({
  baseUrl: API_BASE_URL,
  // Resolved per call rather than captured at module load, so a test (or a
  // future instrumentation wrapper) can replace globalThis.fetch.
  fetch: (request) => globalThis.fetch(request),
});

type FetchResult<T> = {
  data?: T;
  error?: unknown;
  response: Response;
};

/**
 * Turns openapi-fetch's `{data, error}` into a value or a throw, because
 * TanStack Query decides loading, error and retry from the thrown error.
 */
export const unwrap = <T>(result: FetchResult<T>): T => {
  if (!result.response.ok) {
    throw ApiError.from(result.response, result.error);
  }
  if (result.data === undefined) {
    // 204s are the only legitimate empty body in the contract.
    return undefined as T;
  }
  return result.data;
};

/** Distinguishes "the API said no" from "the API was never reached". */
export const request = async <T>(
  call: () => Promise<FetchResult<T>>,
): Promise<T> => {
  let result: FetchResult<T>;
  try {
    result = await call();
  } catch (cause) {
    throw new NetworkError(cause);
  }
  return unwrap(result);
};

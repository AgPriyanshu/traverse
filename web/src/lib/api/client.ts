import createClient from "openapi-fetch";
import { ApiError, NetworkError } from "./errors";
import type { paths } from "./schema";

/**
 * Empty, so every request is same-origin: the API serves no CORS headers, and
 * `/api` is proxied by Vite in dev and by nginx in the container.
 * `VITE_API_BASE_URL` names the proxy target, not the browser's origin.
 */
export const API_BASE_URL = "";

export const client = createClient<paths>({ baseUrl: API_BASE_URL });

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

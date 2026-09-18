import type { Schemas } from "./types";

/** Every documented 404/422/501 body matches this now that ErrorOut is real
 * (SCR-9) — an undocumented status (a bare 500) may still send anything, so
 * this stays a type guard rather than an assumption. */
const isErrorOut = (body: unknown): body is Schemas["ErrorOut"] => {
  return body !== null && typeof body === "object" && "detail" in body;
};

const detailOf = (body: unknown): string | undefined => {
  if (typeof body === "string") { return body; }
  if (!isErrorOut(body)) { return undefined; }

  const { detail } = body;
  if (typeof detail === "string") { return detail; }

  // FastAPI's 422 list items are `{loc, msg, type}`; ErrorOut types them
  // loosely (`Record<string, unknown>[]`) since that shape is FastAPI's own,
  // not this contract's.
  const messages = detail
    .map((item) => {
      const { loc, msg } = item as { loc?: unknown; msg?: unknown };
      if (typeof msg !== "string") { return undefined; }
      const where = Array.isArray(loc) ? loc.join(".") : undefined;
      return where ? `${where}: ${msg}` : msg;
    })
    .filter((message): message is string => Boolean(message));

  return messages.length > 0 ? messages.join("; ") : undefined;
};

export class ApiError extends Error {
  readonly status: number;
  readonly statusText: string;
  readonly url: string;
  readonly detail?: string;

  constructor(init: {
    status: number;
    statusText: string;
    url: string;
    detail?: string;
  }) {
    super(init.detail ?? `${init.status} ${init.statusText}`.trim());
    this.name = "ApiError";
    this.status = init.status;
    this.statusText = init.statusText;
    this.url = init.url;
    this.detail = init.detail;
  }

  static from(response: Response, body: unknown): ApiError {
    return new ApiError({
      status: response.status,
      statusText: response.statusText,
      url: response.url,
      detail: detailOf(body),
    });
  }

  /** The endpoint is frozen in the contract but its handler has not landed. */
  get isNotImplemented(): boolean {
    return this.status === 501;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }
}

/** The error the network layer throws when the request never reached the API. */
export class NetworkError extends Error {
  constructor(cause: unknown) {
    super("Could not reach the Traverse API.");
    this.name = "NetworkError";
    this.cause = cause;
  }
}

export const isApiError = (error: unknown): error is ApiError => {
  return error instanceof ApiError;
};

/**
 * One sentence a reader can act on. A 501 is a real state this sprint, not a
 * bug, and it must not render as "Something went wrong".
 */
export const describeError = (error: unknown): string => {
  if (error instanceof NetworkError) {
    return "Could not reach the Traverse API. Check that it is running, then retry.";
  }

  if (isApiError(error)) {
    if (error.isNotImplemented) {
      return error.detail ?? "This endpoint is not implemented yet.";
    }
    if (error.isNotFound) {
      return error.detail ?? "Not found.";
    }
    if (error.status === 422) {
      return error.detail ?? "The request was rejected as invalid.";
    }
    if (error.status >= 500) {
      return error.detail ?? "The API failed to handle the request.";
    }
    return error.detail ?? `Request failed (${error.status}).`;
  }

  if (error instanceof Error && error.message) { return error.message; }

  return "Something went wrong.";
};

/** Short label for the error surface, above `describeError`'s sentence. */
export const titleForError = (error: unknown): string => {
  if (error instanceof NetworkError) { return "API unreachable"; }
  if (isApiError(error) && error.isNotImplemented) { return "Not built yet"; }
  if (isApiError(error) && error.isNotFound) { return "Not found"; }
  return "Something went wrong";
};

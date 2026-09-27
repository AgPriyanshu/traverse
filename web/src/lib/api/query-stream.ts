import { API_BASE_URL } from "./client";
import { ApiError, NetworkError } from "./errors";
import type { ClarifyResponse, QueryEvent, QueryRequest } from "./types";

export type StreamOptions = {
  signal?: AbortSignal;
  /** Swapped in tests for a `fetch` that never touches the network. */
  fetchImpl?: typeof fetch;
};

const parseFrame = (frame: string): QueryEvent | null => {
  const dataLines = frame
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart());
  if (dataLines.length === 0) { return null; }

  try {
    // The wire payload is the bare discriminated `QueryEvent` union, not the
    // `QueryEventEnvelope` it is documented under — that envelope exists only
    // so `openapi-typescript` emits a real union rather than `unknown`
    // (`api/contracts/api.py`'s `QueryEventEnvelope` doc comment).
    return JSON.parse(dataLines.join("\n")) as QueryEvent;
  } catch {
    return null;
  }
};

/**
 * Reads a `text/event-stream` response as `QueryEvent`s. Frames are separated
 * by a blank line; `event:`/`id:`/`retry:` lines and comments (`:`) are
 * tolerated and ignored rather than treated as a parse failure, so the
 * backend can add them later without this needing a matching change.
 */
async function* readEventStream(
  response: Response,
): AsyncGenerator<QueryEvent, void, undefined> {
  const body = response.body;
  if (!body) { return; }

  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) { break; }
      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = parseFrame(frame);
        if (event) { yield event; }
        boundary = buffer.indexOf("\n\n");
      }
    }

    const finalFrame = buffer.trim();
    if (finalFrame) {
      const event = parseFrame(finalFrame);
      if (event) { yield event; }
    }
  } finally {
    reader.releaseLock();
  }
}

const parseErrorBody = async (response: Response): Promise<unknown> => {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
};

async function* postEventStream(
  path: string,
  body: unknown,
  options: StreamOptions,
): AsyncGenerator<QueryEvent, void, undefined> {
  const { signal, fetchImpl = (input: RequestInfo | URL, init?: RequestInit) => globalThis.fetch(input, init) } = options;
  const base = API_BASE_URL || window.location.origin;
  const url = new URL(path, base);

  let response: Response;
  try {
    response = await fetchImpl(url.toString(), {
      method: "POST",
      headers: { "content-type": "application/json", accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (cause) {
    throw new NetworkError(cause);
  }

  if (!response.ok) {
    throw ApiError.from(
      {
        status: response.status,
        statusText: response.statusText,
        url: response.url || url.toString(),
      },
      await parseErrorBody(response),
    );
  }

  yield* readEventStream(response);
}

/** `POST /api/query` — the initial question. */
export const streamQuery = (
  body: QueryRequest,
  options: StreamOptions = {},
): AsyncGenerator<QueryEvent, void, undefined> => postEventStream("/api/query", body, options);

/** `POST /api/query/{thread_id}/respond` — resumes a stream paused on an `InterruptEvent`. */
export const streamRespond = (
  threadId: string,
  body: ClarifyResponse,
  options: StreamOptions = {},
): AsyncGenerator<QueryEvent, void, undefined> =>
  postEventStream(`/api/query/${threadId}/respond`, body, options);

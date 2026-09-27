import { describe, expect, it, vi } from "vitest";
import { ApiError, NetworkError } from "@/lib/api";
import { streamQuery, streamRespond } from "@/lib/api/query-stream";

const sseResponse = (frames: string[], init: ResponseInit = {}) => {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const frame of frames) {
        controller.enqueue(encoder.encode(frame));
      }
      controller.close();
    },
  });
  return new Response(body, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
    ...init,
  });
};

const collect = async <T>(gen: AsyncGenerator<T, void, undefined>): Promise<T[]> => {
  const out: T[] = [];
  for await (const value of gen) { out.push(value); }
  return out;
};

describe("streamQuery", () => {
  it("parses one QueryEvent per SSE frame", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      sseResponse([
        'data: {"type":"token","text":"Elizabeth"}\n\n',
        'data: {"type":"citation","index":0,"citation":{"book_id":"b-1","page_start":214,"page_end":214}}\n\n',
        'data: {"type":"done","thread_id":"t-1","citation_count":1,"abstained":false}\n\n',
      ]),
    );

    const events = await collect(
      streamQuery(
        { project_id: "p-1", question: "Who is Elizabeth?", thread_id: null, limit_book_order: null, limit_chapter: null },
        { fetchImpl },
      ),
    );

    expect(events).toEqual([
      { type: "token", text: "Elizabeth" },
      { type: "citation", index: 0, citation: { book_id: "b-1", page_start: 214, page_end: 214 } },
      { type: "done", thread_id: "t-1", citation_count: 1, abstained: false },
    ]);
  });

  it("reassembles a frame split across chunks", async () => {
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        const encoder = new TextEncoder();
        controller.enqueue(encoder.encode('data: {"type":"token",'));
        controller.enqueue(encoder.encode('"text":"Darcy"}\n\n'));
        controller.close();
      },
    });
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } }),
    );

    const events = await collect(
      streamQuery(
        { project_id: "p-1", question: "Who is Darcy?", thread_id: null, limit_book_order: null, limit_chapter: null },
        { fetchImpl },
      ),
    );

    expect(events).toEqual([{ type: "token", text: "Darcy" }]);
  });

  it("tolerates event:/id: lines around a data: line", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      sseResponse(['event: message\nid: 1\ndata: {"type":"token","text":"hi"}\n\n']),
    );

    const events = await collect(
      streamQuery(
        { project_id: "p-1", question: "q", thread_id: null, limit_book_order: null, limit_chapter: null },
        { fetchImpl },
      ),
    );

    expect(events).toEqual([{ type: "token", text: "hi" }]);
  });

  it("throws ApiError on a non-2xx initial response", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not implemented yet — owned by be2, S6.5." }), {
        status: 501,
        statusText: "Not Implemented",
        headers: { "content-type": "application/json" },
      }),
    );

    const gen = streamQuery(
      { project_id: "p-1", question: "q", thread_id: null, limit_book_order: null, limit_chapter: null },
      { fetchImpl },
    );

    await expect(collect(gen)).rejects.toBeInstanceOf(ApiError);
  });

  it("throws NetworkError when the transport itself fails", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new Error("offline"));

    const gen = streamQuery(
      { project_id: "p-1", question: "q", thread_id: null, limit_book_order: null, limit_chapter: null },
      { fetchImpl },
    );

    await expect(collect(gen)).rejects.toBeInstanceOf(NetworkError);
  });
});

describe("streamRespond", () => {
  it("posts to the thread's respond endpoint", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      sseResponse(['data: {"type":"token","text":"resumed"}\n\n']),
    );

    const events = await collect(streamRespond("t-1", { answer: "Elizabeth Bennet" }, { fetchImpl }));

    expect(events).toEqual([{ type: "token", text: "resumed" }]);
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/query/t-1/respond");
    expect(JSON.parse(init.body as string)).toEqual({ answer: "Elizabeth Bennet" });
  });
});

import { describe, expect, it, vi } from "vitest";
import { ApiError, NetworkError } from "@/lib/api";
import { uploadMultipart } from "@/lib/api/upload";

/**
 * A minimal fake standing in for `XMLHttpRequest` — jsdom's real one tries to
 * hit the network, and `uploadMultipart` is exercised entirely through the
 * handlers it wires up, not through an actual request.
 */
class FakeXhr {
  status = 0;
  statusText = "";
  responseText = "";
  responseURL = "";
  responseType = "";
  upload = { onprogress: null as ((event: ProgressEvent) => void) | null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  openedUrl = "";
  sentBody: unknown;

  open(_method: string, url: string) {
    this.openedUrl = url;
  }

  send(body: unknown) {
    this.sentBody = body;
  }
}

const settle = (
  xhr: FakeXhr,
  status: number,
  body: unknown,
  statusText = "",
) => {
  xhr.status = status;
  xhr.statusText = statusText;
  xhr.responseText = JSON.stringify(body);
  xhr.responseURL = xhr.openedUrl;
  xhr.onload?.();
};

describe("uploadMultipart", () => {
  it("resolves with the parsed body on a 2xx status", async () => {
    let created: FakeXhr | undefined;
    const promise = uploadMultipart<{ id: string }>({
      path: "/api/projects/p-1/books",
      form: new FormData(),
      createXhr: () => {
        created = new FakeXhr();
        return created as unknown as XMLHttpRequest;
      },
    });

    settle(created as unknown as FakeXhr, 202, { id: "book-1" });
    await expect(promise).resolves.toEqual({ id: "book-1" });
  });

  it("reports real upload progress from XMLHttpRequest.upload", () => {
    const events: number[] = [];
    let created: FakeXhr | undefined;
    void uploadMultipart({
      path: "/api/projects/p-1/books",
      form: new FormData(),
      onProgress: (progress) => events.push(progress.percent),
      createXhr: () => {
        created = new FakeXhr();
        return created as unknown as XMLHttpRequest;
      },
    });

    created?.upload.onprogress?.(
      { lengthComputable: true, loaded: 50, total: 200 } as ProgressEvent,
    );
    created?.upload.onprogress?.(
      { lengthComputable: true, loaded: 200, total: 200 } as ProgressEvent,
    );

    expect(events).toEqual([25, 100]);
  });

  it("ignores a progress event with no known total", () => {
    const onProgress = vi.fn();
    let created: FakeXhr | undefined;
    void uploadMultipart({
      path: "/api/projects/p-1/books",
      form: new FormData(),
      onProgress,
      createXhr: () => {
        created = new FakeXhr();
        return created as unknown as XMLHttpRequest;
      },
    });

    created?.upload.onprogress?.(
      { lengthComputable: false, loaded: 50, total: 0 } as ProgressEvent,
    );
    expect(onProgress).not.toHaveBeenCalled();
  });

  it("rejects a non-2xx status with an ApiError carrying the parsed detail", async () => {
    let created: FakeXhr | undefined;
    const promise = uploadMultipart({
      path: "/api/projects/p-1/books",
      form: new FormData(),
      createXhr: () => {
        created = new FakeXhr();
        return created as unknown as XMLHttpRequest;
      },
    });

    settle(created as unknown as FakeXhr, 422, { detail: "file too large" }, "Unprocessable Entity");

    await expect(promise).rejects.toBeInstanceOf(ApiError);
    await promise.catch((error: ApiError) => {
      expect(error.status).toBe(422);
      expect(error.detail).toBe("file too large");
    });
  });

  it("rejects with a NetworkError when the transport itself fails", async () => {
    let created: FakeXhr | undefined;
    const promise = uploadMultipart({
      path: "/api/projects/p-1/books",
      form: new FormData(),
      createXhr: () => {
        created = new FakeXhr();
        return created as unknown as XMLHttpRequest;
      },
    });

    created?.onerror?.();
    await expect(promise).rejects.toBeInstanceOf(NetworkError);
  });

  it("appends every query parameter except null and undefined", () => {
    let created: FakeXhr | undefined;
    void uploadMultipart({
      path: "/api/projects/p-1/books",
      query: { series_order: null, keep: "1" },
      form: new FormData(),
      createXhr: () => {
        created = new FakeXhr();
        return created as unknown as XMLHttpRequest;
      },
    });

    expect(created?.openedUrl).toContain("keep=1");
    expect(created?.openedUrl).not.toContain("series_order");
  });
});

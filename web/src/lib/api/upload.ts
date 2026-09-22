import { API_BASE_URL } from "./client";
import { ApiError, NetworkError } from "./errors";

export type UploadProgress = {
  loaded: number;
  total: number;
  percent: number;
};

export type MultipartUploadOptions = {
  path: string;
  query?: Record<string, string | number | null | undefined>;
  form: FormData;
  onProgress?: (progress: UploadProgress) => void;
  signal?: AbortSignal;
  /** Swapped in tests for a fake that never touches the network. */
  createXhr?: () => XMLHttpRequest;
};

/**
 * `fetch` reports no upload progress — only `XMLHttpRequest.upload.onprogress`
 * does — and a 200 MB file behind a spinner with no movement reads as frozen
 * (S2.11). This is the one client call that goes around `openapi-fetch` for
 * that reason; its errors still resolve to `ApiError`/`NetworkError` via
 * `ApiError.from`'s structural `Response` subset, so callers see one error
 * shape regardless of which transport produced it.
 */
export const uploadMultipart = <T>(options: MultipartUploadOptions): Promise<T> => {
  const {
    path,
    query,
    form,
    onProgress,
    signal,
    createXhr = () => new XMLHttpRequest(),
  } = options;

  const base = API_BASE_URL || window.location.origin;
  const url = new URL(path, base);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== null && value !== undefined) {
      url.searchParams.set(key, String(value));
    }
  }

  return new Promise<T>((resolve, reject) => {
    const xhr = createXhr();
    xhr.open("POST", url.toString());
    xhr.responseType = "text";

    xhr.upload.onprogress = (event) => {
      if (!onProgress || !event.lengthComputable) { return; }
      onProgress({
        loaded: event.loaded,
        total: event.total,
        percent: (event.loaded / event.total) * 100,
      });
    };

    xhr.onerror = () => { reject(new NetworkError(new Error("Upload failed at the network layer."))); };
    xhr.onabort = () => { reject(new NetworkError(new Error("Upload aborted."))); };
    xhr.ontimeout = () => { reject(new NetworkError(new Error("Upload timed out."))); };

    xhr.onload = () => {
      let body: unknown;
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : undefined;
      } catch (cause) {
        reject(new NetworkError(cause));
        return;
      }

      if (xhr.status < 200 || xhr.status >= 300) {
        reject(
          ApiError.from(
            {
              status: xhr.status,
              statusText: xhr.statusText,
              url: xhr.responseURL || url.toString(),
            },
            body,
          ),
        );
        return;
      }

      resolve(body as T);
    };

    if (signal) {
      if (signal.aborted) {
        xhr.abort();
        return;
      }
      signal.addEventListener("abort", () => { xhr.abort(); });
    }

    xhr.send(form);
  });
};

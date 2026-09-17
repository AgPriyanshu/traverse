import { describe, expect, it } from "vitest";
import {
  MAX_UPLOAD_BYTES,
  validateUpload,
} from "@/routes/books/validate-upload";

const file = (over: Partial<Parameters<typeof validateUpload>[0]> = {}) => ({
  name: "pride-and-prejudice.pdf",
  size: 4 * 1024 * 1024,
  type: "application/pdf",
  ...over,
});

describe("validateUpload", () => {
  it("accepts a reasonable PDF", () => {
    expect(validateUpload(file())).toBeNull();
  });

  it("accepts a PDF whose MIME type the browser did not fill in", () => {
    expect(validateUpload(file({ type: "" }))).toBeNull();
  });

  it("rejects a non-PDF and says what to do", () => {
    expect(validateUpload(file({ name: "novel.epub", type: "application/epub+zip" }))).toMatch(
      /PDF/,
    );
  });

  it("rejects an empty file", () => {
    expect(validateUpload(file({ size: 0 }))).toBe("That file is empty.");
  });

  it("rejects an oversized file and names both sizes", () => {
    const message = validateUpload(file({ size: MAX_UPLOAD_BYTES + 1 }));
    expect(message).toContain("200 MB");
    expect(message).toMatch(/200\.0 MB|200 MB/);
  });

  it("accepts a file exactly at the cap", () => {
    expect(validateUpload(file({ size: MAX_UPLOAD_BYTES }))).toBeNull();
  });
});

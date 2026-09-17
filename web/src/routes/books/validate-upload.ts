import { formatBytes } from "@/lib/format";

/** PRD F1.1 caps an upload at 200 MB; anything larger is rejected in the browser. */
export const MAX_UPLOAD_BYTES = 200 * 1024 * 1024;

export type UploadCandidate = {
  name: string;
  size: number;
  type: string;
};

/**
 * Returns the message to show, or null when the file is acceptable. The
 * message names the actual size, because "file too large" without a number
 * leaves the reader to guess what to do about it.
 */
export const validateUpload = (file: UploadCandidate): string | null => {
  const isPdf =
    file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");

  if (!isPdf) {
    return "Traverse reads PDFs. Convert the file to PDF and try again.";
  }

  if (file.size === 0) {
    return "That file is empty.";
  }

  if (file.size > MAX_UPLOAD_BYTES) {
    return `That file is ${formatBytes(file.size)}. The limit is ${formatBytes(
      MAX_UPLOAD_BYTES,
    )} — split the volume, or upload each book of a series separately.`;
  }

  return null;
};

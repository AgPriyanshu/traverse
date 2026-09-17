import type { BookStatus, StageState } from "@/lib/api";

export type StatusTone = "ok" | "warn" | "err" | "busy" | "idle";

export const TONE_COLOR: Record<StatusTone, string> = {
  ok: "status.ok",
  warn: "status.warn",
  err: "status.err",
  busy: "accent.solid",
  idle: "status.idle",
};

const BOOK_STATUS: Record<BookStatus, { tone: StatusTone; label: string }> = {
  queued: { tone: "idle", label: "Queued" },
  processing: { tone: "busy", label: "Processing" },
  ready: { tone: "ok", label: "Ready" },
  failed: { tone: "err", label: "Failed" },
};

const STAGE_STATE: Record<StageState, { tone: StatusTone; label: string }> = {
  pending: { tone: "idle", label: "Pending" },
  running: { tone: "busy", label: "Running" },
  succeeded: { tone: "ok", label: "Done" },
  failed: { tone: "err", label: "Failed" },
  skipped: { tone: "idle", label: "Skipped" },
};

export const toneForBookStatus = (status: BookStatus) => BOOK_STATUS[status];
export const toneForStageState = (state: StageState) => STAGE_STATE[state];

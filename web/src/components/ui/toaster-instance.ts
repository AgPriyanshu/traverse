import { createToaster } from "@chakra-ui/react";

/**
 * A shared singleton rather than a hook, so a mutation's `onSuccess` (outside
 * any component render) can raise one — the already-ingested upload redirect
 * needs to say why it redirected from code that runs after navigation starts.
 */
export const toaster = createToaster({
  placement: "bottom-end",
  pauseOnPageIdle: true,
});

export const TOAST_TONE_COLOR: Record<string, string> = {
  success: "status.ok",
  error: "status.err",
  info: "fg",
  warning: "status.warn",
};

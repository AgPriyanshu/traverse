import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

/**
 * False on the server and on the first client render, true afterwards. Used
 * where a control must not label itself before the resolved theme is known.
 */
export const useHydrated = (): boolean => {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
};

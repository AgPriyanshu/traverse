export const SESSION_TOKEN_HEADER = "X-Session-Token";

const STORAGE_KEY = "traverse:session-token";

export const loadSessionToken = (): string | null => {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
};

export const saveSessionToken = (token: string): void => {
  try {
    window.localStorage.setItem(STORAGE_KEY, token);
  } catch {
    // The projects this session created just won't stay visible after a reload.
  }
};
